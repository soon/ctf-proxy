from psycopg import Cursor


class RuleSourceTable:
    def list(self, tx: Cursor, status: str | None = None) -> list:
        if status is None:
            tx.execute(
                "SELECT name, status, source FROM dashboard.rule_source "
                "ORDER BY status DESC, name ASC"
            )
        else:
            tx.execute(
                "SELECT name, status, source FROM dashboard.rule_source "
                "WHERE status = %s ORDER BY name ASC",
                (status,),
            )
        return tx.fetchall()

    def get(self, tx: Cursor, name: str, status: str) -> str | None:
        tx.execute(
            "SELECT source FROM dashboard.rule_source WHERE name = %s AND status = %s",
            (name, status),
        )
        row = tx.fetchone()
        return row[0] if row else None

    def upsert(self, tx: Cursor, name: str, status: str, source: str, updated: int) -> None:
        tx.execute(
            """
            INSERT INTO dashboard.rule_source (name, status, source, updated)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (name, status)
            DO UPDATE SET source = excluded.source, updated = excluded.updated
            """,
            (name, status, source, updated),
        )

    def delete(self, tx: Cursor, name: str, status: str) -> bool:
        tx.execute(
            "DELETE FROM dashboard.rule_source WHERE name = %s AND status = %s",
            (name, status),
        )
        return tx.rowcount > 0

    def promote(self, tx: Cursor, name: str) -> bool:
        source = self.get(tx, name, "draft")
        if source is None:
            return False
        self.upsert(tx, name, "enabled", source, self.max_updated(tx) + 1)
        self.delete(tx, name, "draft")
        return True

    def max_updated(self, tx: Cursor, status: str | None = None) -> int:
        if status is None:
            tx.execute("SELECT COALESCE(MAX(updated), 0) FROM dashboard.rule_source")
        else:
            tx.execute(
                "SELECT COALESCE(MAX(updated), 0) FROM dashboard.rule_source WHERE status = %s",
                (status,),
            )
        return tx.fetchone()[0]
