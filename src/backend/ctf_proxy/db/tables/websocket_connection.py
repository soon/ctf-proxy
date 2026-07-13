from dataclasses import dataclass
from typing import ClassVar

from psycopg import Cursor

from ctf_proxy.db.refs import Ref


@dataclass
class WebSocketConnectionRow:
    id: int
    http_request_id: int

    @dataclass
    class Insert:
        TABLE: ClassVar[str] = "websocket_connection"
        RETURNING: ClassVar[bool] = True
        http_request_id: "int | Ref"


class WebSocketConnectionTable:
    def insert(self, tx: Cursor, http_request_id: int) -> int:
        tx.execute(
            """
            INSERT INTO websocket_connection (http_request_id) VALUES (%s) RETURNING id
            """,
            (http_request_id,),
        )
        return tx.fetchone()[0]
