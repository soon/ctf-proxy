import logging
import os
from dataclasses import dataclass

from ctf_proxy.db.adapters import configure_sqlite
from ctf_proxy.db.models import DbProvider

logger = logging.getLogger(__name__)

configure_sqlite()


MINUTE_MS = 60_000


def minute_bucket(timestamp: int | None) -> int | None:
    if timestamp is None:
        return None
    return (timestamp // MINUTE_MS) * MINUTE_MS


@dataclass
class AnalysisResultRow:
    rule_id: int
    tag: str
    meta: str | None = None
    port: int | None = None
    ref_id: int | None = None
    batch_id: str | None = None
    event_time: int | None = None


@dataclass
class BackfillJob:
    id: int
    target_id: int
    ports: list[int] | None
    http_cursor: int
    tcp_cursor: int
    status: str


class RuleTable:
    def get_or_create(self, tx, name: str) -> int:
        tx.execute("INSERT INTO rule (name) VALUES (?) ON CONFLICT(name) DO NOTHING", (name,))
        tx.execute("SELECT id FROM rule WHERE name = ?", (name,))
        return tx.fetchone()[0]


class AnalysisResultTable:
    table: str
    ref_column: str
    source: str

    def insert_many(self, tx, results: list[AnalysisResultRow], created: int) -> None:
        tx.executemany(
            f"""
            INSERT INTO {self.table}
                (rule_id, tag, meta, port, {self.ref_column}, created, event_time, batch_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (r.rule_id, r.tag, r.meta, r.port, r.ref_id, created, r.event_time, r.batch_id)
                for r in results
            ],
        )
        deltas: dict[tuple, int] = {}
        for r in results:
            bucket = minute_bucket(r.event_time)
            if r.port is None or bucket is None:
                continue
            key = (r.port, r.rule_id, r.tag, bucket)
            deltas[key] = deltas.get(key, 0) + 1
        self.apply_tag_time_deltas(tx, deltas)

    def delete_for_refs(self, tx, ref_ids: list[int]) -> None:
        if not ref_ids:
            return
        placeholders = ",".join("?" * len(ref_ids))
        rows = tx.execute(
            f"SELECT port, rule_id, tag, event_time FROM {self.table} "
            f"WHERE {self.ref_column} IN ({placeholders})",
            ref_ids,
        ).fetchall()
        deltas: dict[tuple, int] = {}
        for port, rule_id, tag, event_time in rows:
            bucket = minute_bucket(event_time)
            if port is None or bucket is None:
                continue
            key = (port, rule_id, tag, bucket)
            deltas[key] = deltas.get(key, 0) - 1
        self.apply_tag_time_deltas(tx, deltas)
        tx.execute(
            f"DELETE FROM {self.table} WHERE {self.ref_column} IN ({placeholders})",
            ref_ids,
        )

    def apply_tag_time_deltas(self, tx, deltas: dict[tuple, int]) -> None:
        for (port, rule_id, tag, bucket), delta in deltas.items():
            if delta == 0:
                continue
            tx.execute(
                """
                UPDATE tag_time_stats SET count = count + ?
                WHERE port = ? AND rule_id = ? AND tag = ? AND source = ? AND time = ?
                """,
                (delta, port, rule_id, tag, self.source, bucket),
            )
            if not tx.rowcount:
                tx.execute(
                    """
                    INSERT INTO tag_time_stats (port, rule_id, tag, source, time, count)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (port, rule_id, tag, self.source, bucket, delta),
                )


class HttpAnalysisResultTable(AnalysisResultTable):
    table = "http_analysis_result"
    ref_column = "http_request_id"
    source = "http"


class TcpAnalysisResultTable(AnalysisResultTable):
    table = "tcp_analysis_result"
    ref_column = "tcp_connection_id"
    source = "tcp"


class AnalysisCursorTable:
    def get(self, tx, rule_id: int, source: str) -> int:
        tx.execute(
            "SELECT last_id FROM analysis_cursor WHERE rule_id = ? AND source = ?",
            (rule_id, source),
        )
        row = tx.fetchone()
        return row[0] if row else 0

    def set(self, tx, rule_id: int, source: str, last_id: int) -> None:
        tx.execute(
            """
            INSERT INTO analysis_cursor (rule_id, source, last_id) VALUES (?, ?, ?)
            ON CONFLICT(rule_id, source) DO UPDATE SET last_id = excluded.last_id
            """,
            (rule_id, source, last_id),
        )


def encode_ports(ports: list[int] | None) -> str | None:
    if not ports:
        return None
    return ",".join(str(p) for p in ports)


def decode_ports(value: str | None) -> list[int] | None:
    if not value:
        return None
    return [int(p) for p in value.split(",") if p]


class BackfillJobTable:
    def create(self, tx, target_id: int, ports: list[int] | None, created: int) -> int:
        tx.execute(
            """
            INSERT INTO backfill_job (target_id, ports, status, created, updated)
            VALUES (?, ?, 'pending', ?, ?)
            """,
            (target_id, encode_ports(ports), created, created),
        )
        tx.execute("SELECT last_insert_rowid()")
        return tx.fetchone()[0]

    def active(self, tx) -> BackfillJob | None:
        tx.execute(
            """
            SELECT id, target_id, ports, http_cursor, tcp_cursor, status
            FROM backfill_job WHERE status IN ('pending', 'running')
            ORDER BY id LIMIT 1
            """
        )
        row = tx.fetchone()
        return self.row_to_job(row) if row else None

    def latest(self, tx) -> BackfillJob | None:
        tx.execute(
            """
            SELECT id, target_id, ports, http_cursor, tcp_cursor, status
            FROM backfill_job ORDER BY id DESC LIMIT 1
            """
        )
        row = tx.fetchone()
        return self.row_to_job(row) if row else None

    def row_to_job(self, row) -> BackfillJob:
        return BackfillJob(
            id=row[0],
            target_id=row[1],
            ports=decode_ports(row[2]),
            http_cursor=row[3],
            tcp_cursor=row[4],
            status=row[5],
        )

    def update(self, tx, job_id: int, updated: int, **fields) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values())
        tx.execute(
            f"UPDATE backfill_job SET {assignments}, updated = ? WHERE id = ?",
            (*values, updated, job_id),
        )


class AnalysisDB:
    def __init__(self, db_file: str = "analysis.db", db_provider: type[DbProvider] = DbProvider):
        self.db_file = db_file
        self.db_provider = db_provider(db_file)
        self.rules = RuleTable()
        self.http_results = HttpAnalysisResultTable()
        self.tcp_results = TcpAnalysisResultTable()
        self.cursors = AnalysisCursorTable()
        self.backfill = BackfillJobTable()

    def connect(self):
        return self.db_provider.connect()

    def init_schema(self, schema_file: str | None = None) -> None:
        if schema_file is None:
            schema_file = os.path.join(os.path.dirname(__file__), "schema.sql")

        with open(schema_file) as f:
            schema_sql = f.read()

        with self.connect() as conn:
            conn.executescript(schema_sql)
            self.migrate(conn)

        logger.info(f"Analysis database schema initialized from {schema_file}")

    def migrate(self, conn) -> None:
        for table in ("http_analysis_result", "tcp_analysis_result"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "event_time" not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN event_time INTEGER")

    def init_db(self) -> None:
        self.init_schema()
        logger.info(f"Analysis database initialized: {self.db_file}")

    def tag_stats(self, port: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.name AS rule, s.tag AS tag, s.source AS source, SUM(s.count) AS n
                FROM tag_time_stats s
                JOIN rule r ON r.id = s.rule_id
                WHERE s.port = ?
                GROUP BY r.name, s.tag, s.source
                """,
                (port,),
            ).fetchall()

        merged: dict[tuple[str, str], dict] = {}
        for rule, tag, source, n in rows:
            entry = merged.setdefault(
                (rule, tag), {"rule": rule, "tag": tag, "http_count": 0, "tcp_count": 0, "total": 0}
            )
            entry[f"{source}_count"] += n
            entry["total"] += n
        return sorted(merged.values(), key=lambda e: e["total"], reverse=True)

    def tag_time_series(self, port: int, since: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.name AS rule, s.tag AS tag, s.time AS time, SUM(s.count) AS n
                FROM tag_time_stats s
                JOIN rule r ON r.id = s.rule_id
                WHERE s.port = ? AND s.time >= ?
                GROUP BY r.name, s.tag, s.time
                ORDER BY s.time
                """,
                (port, since),
            ).fetchall()

        series: dict[tuple[str, str], dict] = {}
        for rule, tag, time, n in rows:
            entry = series.setdefault(
                (rule, tag), {"rule": rule, "tag": tag, "total": 0, "time_series": []}
            )
            entry["time_series"].append({"timestamp": time, "count": n})
            entry["total"] += n
        return sorted(series.values(), key=lambda e: e["total"], reverse=True)

    def analysis_for_ref(self, source_type: str, ref_id: int) -> list[dict]:
        table = "http_analysis_result" if source_type == "http" else "tcp_analysis_result"
        ref_column = "http_request_id" if source_type == "http" else "tcp_connection_id"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT r.name AS rule, res.tag AS tag, res.meta AS meta
                FROM {table} res
                JOIN rule r ON r.id = res.rule_id
                WHERE res.{ref_column} = ?
                ORDER BY res.id
                """,
                (ref_id,),
            ).fetchall()
        return [{"rule": row[0], "tag": row[1], "meta": row[2]} for row in rows]

    def tags_for_refs(
        self, source_type: str, ids: list[int], rules: list[str] | None
    ) -> dict[int, list[str]]:
        if not ids:
            return {}
        table = "http_analysis_result" if source_type == "http" else "tcp_analysis_result"
        ref_column = "http_request_id" if source_type == "http" else "tcp_connection_id"
        id_placeholders = ",".join("?" * len(ids))
        params: list = list(ids)
        rule_clause = ""
        if rules:
            rule_placeholders = ",".join("?" * len(rules))
            rule_clause = f" AND r.name IN ({rule_placeholders})"
            params.extend(rules)

        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT res.{ref_column} AS ref_id, res.tag AS tag
                FROM {table} res
                JOIN rule r ON r.id = res.rule_id
                WHERE res.{ref_column} IN ({id_placeholders}){rule_clause}
                ORDER BY res.id
                """,
                params,
            ).fetchall()

        result: dict[int, list[str]] = {}
        for ref_id, tag in rows:
            tags = result.setdefault(ref_id, [])
            if tag not in tags:
                tags.append(tag)
        return result


def make_analysis_db(
    path: str = "analysis.db", db_provider: type[DbProvider] = DbProvider
) -> AnalysisDB:
    db = AnalysisDB(path, db_provider=db_provider)
    db.init_db()
    return db
