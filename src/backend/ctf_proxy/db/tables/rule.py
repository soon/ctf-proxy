from psycopg import Cursor


class RuleTable:
    def get_or_create(self, tx: Cursor, name: str) -> int:
        tx.execute("INSERT INTO rule (name) VALUES (%s) ON CONFLICT(name) DO NOTHING", (name,))
        tx.execute("SELECT id FROM rule WHERE name = %s", (name,))
        return tx.fetchone()[0]
