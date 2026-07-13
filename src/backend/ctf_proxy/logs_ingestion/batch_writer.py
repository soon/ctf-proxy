import logging
from dataclasses import fields
from time import perf_counter

import psycopg
from psycopg import Cursor

from ctf_proxy.db.connection import nul_safe
from ctf_proxy.db.refs import Ref
from ctf_proxy.db.tables.flag import FlagRow
from ctf_proxy.db.tables.http_request import HttpRequestRow
from ctf_proxy.db.tables.http_response import HttpResponseRow
from ctf_proxy.db.tables.session import SessionRow
from ctf_proxy.db.tables.session_link import SessionLinkRow
from ctf_proxy.db.tables.websocket_connection import WebSocketConnectionRow
from ctf_proxy.db.tables.websocket_frame import WebSocketFrameRow

logger = logging.getLogger(__name__)

MAX_ROWS_PER_INSERT = 1000

# SQLSTATE classes that mean "this specific row's content is bad" (deterministic —
# will always fail), so the row can be dropped: 22=data exception, 23=integrity
# constraint violation. Plus 54000=program_limit_exceeded (e.g. index row too large).
# Everything else (connection loss, admin shutdown, out-of-resources, code bugs) is
# transient/global and must NOT drop rows — it aborts the flush so the batch is retried.
BAD_ROW_SQLSTATE_CLASSES = ("22", "23")
BAD_ROW_SQLSTATES = {"54000"}


def is_bad_row_error(e: psycopg.Error) -> bool:
    code = getattr(e, "sqlstate", None)
    if not code:
        return False
    return code[:2] in BAD_ROW_SQLSTATE_CLASSES or code in BAD_ROW_SQLSTATES

# Tables flushed in dependency order: a row is inserted only after every Ref it
# references has been resolved by an earlier table.
FLUSH_ORDER = [
    HttpRequestRow.Insert,
    HttpResponseRow.Insert,
    WebSocketConnectionRow.Insert,
    FlagRow.Insert,
    WebSocketFrameRow.Insert,
    SessionLinkRow.Insert,
]


def columns_of(insert_cls) -> list[str]:
    return [f.name for f in fields(insert_cls)]


def flush_objects(tx: Cursor, objs: list, isolate: bool = False) -> list:
    """Bulk-insert a homogeneous list of Insert dataclasses, resolving Ref params.

    Returns a list aligned to objs: the new id (for RETURNING tables), True, or
    None when the row was dropped (unresolved Ref, or isolated as a bad row).
    """
    result: list = [None] * len(objs)
    if not objs:
        return result

    insert_cls = type(objs[0])
    columns = columns_of(insert_cls)
    returning = getattr(insert_cls, "RETURNING", False)
    conflict = getattr(insert_cls, "CONFLICT", "")

    live_index: list[int] = []
    rows: list[list] = []
    for i, obj in enumerate(objs):
        row = []
        drop = False
        for name in columns:
            value = getattr(obj, name)
            if isinstance(value, Ref):
                if not value.resolved:
                    drop = True
                    break
                value = value.value
            row.append(nul_safe(value))
        if drop:
            continue
        live_index.append(i)
        rows.append(row)

    if not rows:
        return result

    ids = insert_rows(
        tx, insert_cls.TABLE, columns, rows,
        returning=returning, conflict=conflict, isolate=isolate,
    )
    for i, row_id in zip(live_index, ids, strict=True):
        result[i] = row_id
    return result


def flush_with_isolation_fallback(tx: Cursor, do_flush, reset) -> None:
    """Flush with no per-row savepoints; on any failure roll back the whole
    flush and retry once with per-row savepoints + binary-search isolation."""
    try:
        with tx.connection.transaction():
            do_flush(False)
    except psycopg.Error as e:
        if not is_bad_row_error(e):
            # transient/global (connection lost, shutdown, out-of-resources): do NOT
            # drop rows — propagate so the batch is retried without advancing.
            raise
        logger.warning(f"Batch flush failed ({e}); retrying with per-row isolation")
        reset()
        do_flush(True)


class Batch:
    def __init__(self):
        self.ops: dict[type, list[tuple]] = {}
        self.session_refs: dict[tuple, list] = {}

    def insert(self, obj) -> Ref | None:
        ref = Ref() if getattr(type(obj), "RETURNING", False) else None
        self.ops.setdefault(type(obj), []).append((obj, ref))
        return ref

    def insert_many(self, objs: list) -> None:
        for obj in objs:
            self.ops.setdefault(type(obj), []).append((obj, None))

    def session(self, port: int, key: str) -> Ref:
        entry = self.session_refs.get((port, key))
        if entry is None:
            ref = Ref()
            self.session_refs[(port, key)] = [ref, 1]
            return ref
        entry[1] += 1
        return entry[0]

    def reset(self) -> None:
        for ops in self.ops.values():
            for _, ref in ops:
                if ref is not None:
                    ref.value = None
                    ref.resolved = False
        for entry in self.session_refs.values():
            entry[0].value = None
            entry[0].resolved = False

    def flush(self, tx: Cursor, isolate: bool = False) -> None:
        self.flush_sessions(tx, isolate)
        for insert_cls in FLUSH_ORDER:
            self.flush_ops(tx, insert_cls, isolate)

    def flush_tables_timed(self, tx: Cursor) -> dict[str, float]:
        """TEMP diagnostic: flush each table in its OWN transaction (commit per table)
        and return {table: seconds}. No isolation fallback — for measurement only."""
        timings: dict[str, float] = {}
        if self.session_refs:
            t = perf_counter()
            self.flush_sessions(tx, isolate=False)
            tx.connection.commit()
            timings["session"] = perf_counter() - t
        for insert_cls in FLUSH_ORDER:
            if not self.ops.get(insert_cls):
                continue
            t = perf_counter()
            self.flush_ops(tx, insert_cls, isolate=False)
            tx.connection.commit()
            timings[insert_cls.TABLE] = perf_counter() - t
        return timings

    def flush_sessions(self, tx: Cursor, isolate: bool = False) -> None:
        if not self.session_refs:
            return
        items = list(self.session_refs.items())
        objs = [SessionRow.Insert(port=port, key=key, count=entry[1]) for (port, key), entry in items]
        ids = flush_objects(tx, objs, isolate=isolate)
        for (_, entry), row_id in zip(items, ids, strict=True):
            if row_id is not None:
                entry[0].value = row_id
                entry[0].resolved = True

    def flush_ops(self, tx: Cursor, insert_cls, isolate: bool = False) -> None:
        ops = self.ops.get(insert_cls)
        if not ops:
            return
        ids = flush_objects(tx, [obj for obj, _ in ops], isolate=isolate)
        for (_, ref), row_id in zip(ops, ids, strict=True):
            if ref is not None and row_id is not None:
                ref.value = row_id
                ref.resolved = True


def insert_rows(
    tx: Cursor,
    table: str,
    columns: list[str],
    rows: list[list],
    returning: bool = False,
    conflict: str = "",
    isolate: bool = False,
) -> list:
    result: list = [None] * len(rows)
    cols_sql = ", ".join(f'"{c}"' for c in columns)
    row_placeholder = "(" + ", ".join(["%s"] * len(columns)) + ")"
    returning_sql = " RETURNING id" if returning else ""

    def run(indices: list[int]) -> None:
        values = ", ".join([row_placeholder] * len(indices))
        params: list = []
        for i in indices:
            params.extend(rows[i])
        sql = f"INSERT INTO {table} ({cols_sql}) VALUES {values} {conflict}{returning_sql}"
        tx.execute(sql, params)
        if returning:
            for i, returned_row in zip(indices, tx.fetchall(), strict=True):
                result[i] = returned_row[0]
        else:
            for i in indices:
                result[i] = True

    def isolate_recurse(indices: list[int]) -> None:
        if not indices:
            return
        try:
            with tx.connection.transaction():
                run(indices)
        except psycopg.Error as e:
            if not is_bad_row_error(e):
                # transient/global error — never drop rows over it; abort the flush.
                raise
            if len(indices) == 1:
                logger.error(f"Dropping bad row {rows[indices[0]]} in {table}: {e}")
                return
            mid = len(indices) // 2
            isolate_recurse(indices[:mid])
            isolate_recurse(indices[mid:])

    for start in range(0, len(rows), MAX_ROWS_PER_INSERT):
        chunk = list(range(start, min(start + MAX_ROWS_PER_INSERT, len(rows))))
        if isolate:
            isolate_recurse(chunk)
        else:
            run(chunk)
    return result
