from dataclasses import dataclass

from psycopg import Cursor


@dataclass
class SessionRow:
    id: int
    port: int
    key: str


class SessionTable:
    def upsert(self, tx: Cursor, port: int, key: str) -> int:
        """Upsert session and increment count. Returns session ID."""
        tx.execute(
            """
            INSERT INTO session (port, key, count)
            VALUES (%s, %s, 1)
            ON CONFLICT(port, key) DO UPDATE SET count = count + 1
            RETURNING id
            """,
            (port, key),
        )
        return tx.fetchone()[0]
