from dataclasses import dataclass
from typing import ClassVar

from psycopg import Cursor

from ctf_proxy.db.refs import Ref


@dataclass
class SessionLinkRow:
    id: int
    session_id: int
    http_request_id: int

    @dataclass
    class Insert:
        TABLE: ClassVar[str] = "session_link"
        CONFLICT: ClassVar[str] = "ON CONFLICT (session_id, http_request_id) DO NOTHING"
        session_id: "int | Ref"
        http_request_id: "int | Ref"


class SessionLinkTable:
    def insert(self, tx: Cursor, row: SessionLinkRow.Insert) -> None:
        tx.execute(
            """
            INSERT INTO session_link (session_id, http_request_id)
            VALUES (%s, %s)
            ON CONFLICT (session_id, http_request_id) DO NOTHING
            """,
            (row.session_id, row.http_request_id),
        )
