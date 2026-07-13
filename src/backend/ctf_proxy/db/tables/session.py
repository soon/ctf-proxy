from dataclasses import dataclass
from typing import ClassVar

from psycopg import Cursor


@dataclass
class SessionRow:
    id: int
    port: int
    key: str

    @dataclass
    class Insert:
        TABLE: ClassVar[str] = "session"
        RETURNING: ClassVar[bool] = True
        CONFLICT: ClassVar[str] = (
            "ON CONFLICT (port, key) DO UPDATE SET count = session.count + EXCLUDED.count"
        )
        port: int
        key: str
        count: int


class SessionTable:
    def upsert(self, tx: Cursor, port: int, key: str) -> int:
        """Upsert session and increment count. Returns session ID."""
        tx.execute(
            """
            INSERT INTO session (port, key, count)
            VALUES (%s, %s, 1)
            ON CONFLICT(port, key) DO UPDATE SET count = session.count + 1
            RETURNING id
            """,
            (port, key),
        )
        return tx.fetchone()[0]
