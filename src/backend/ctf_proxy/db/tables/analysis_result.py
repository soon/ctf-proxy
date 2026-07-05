from dataclasses import dataclass

from psycopg import Cursor

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


class AnalysisResultTable:
    table: str
    ref_column: str
    source: str

    def insert_many(
        self, tx: Cursor, results: list[AnalysisResultRow], created: int
    ) -> None:
        tx.executemany(
            f"""
            INSERT INTO {self.table}
                (rule_id, tag, meta, port, {self.ref_column}, created, event_time, batch_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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

    def delete_for_refs(self, tx: Cursor, ref_ids: list[int]) -> None:
        if not ref_ids:
            return
        placeholders = ",".join(["%s"] * len(ref_ids))
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

    def apply_tag_time_deltas(self, tx: Cursor, deltas: dict[tuple, int]) -> None:
        for (port, rule_id, tag, bucket), delta in deltas.items():
            if delta == 0:
                continue
            tx.execute(
                """
                UPDATE tag_time_stats SET count = count + %s
                WHERE port = %s AND rule_id = %s AND tag = %s AND source = %s AND time = %s
                """,
                (delta, port, rule_id, tag, self.source, bucket),
            )
            if not tx.rowcount:
                tx.execute(
                    """
                    INSERT INTO tag_time_stats (port, rule_id, tag, source, time, count)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (port, rule_id, tag, self.source, bucket, delta),
                )
