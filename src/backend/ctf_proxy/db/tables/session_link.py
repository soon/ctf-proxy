from dataclasses import dataclass

from psycopg import Cursor

from ctf_proxy.db.tables.session import SessionTable


@dataclass
class SessionLinkRow:
    id: int
    session_id: int
    http_request_id: int

    @dataclass
    class Insert:
        session_key: str
        port: int
        http_request_id: int


class SessionLinkTable:
    def insert(self, tx: Cursor, row: SessionLinkRow.Insert) -> None:
        session_table = SessionTable()
        session_id = session_table.upsert(tx, row.port, row.session_key)

        tx.execute(
            """
            INSERT INTO session_link (session_id, http_request_id)
            VALUES (%s, %s)
            ON CONFLICT (session_id, http_request_id) DO NOTHING
            """,
            (session_id, row.http_request_id),
        )
