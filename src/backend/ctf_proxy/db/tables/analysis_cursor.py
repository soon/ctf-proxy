from psycopg import Cursor


class AnalysisCursorTable:
    def get(self, tx: Cursor, rule_id: int, source: str) -> int:
        tx.execute(
            "SELECT last_id FROM analysis_cursor WHERE rule_id = %s AND source = %s",
            (rule_id, source),
        )
        row = tx.fetchone()
        return row[0] if row else 0

    def set(self, tx: Cursor, rule_id: int, source: str, last_id: int) -> None:
        tx.execute(
            """
            INSERT INTO analysis_cursor (rule_id, source, last_id) VALUES (%s, %s, %s)
            ON CONFLICT(rule_id, source) DO UPDATE SET last_id = excluded.last_id
            """,
            (rule_id, source, last_id),
        )
