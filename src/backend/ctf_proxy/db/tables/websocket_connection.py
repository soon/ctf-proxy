from dataclasses import dataclass

from psycopg import Cursor


@dataclass
class WebSocketConnectionRow:
    id: int
    http_request_id: int

    @dataclass
    class Insert:
        http_request_id: int


class WebSocketConnectionTable:
    def insert(self, tx: Cursor, http_request_id: int) -> int:
        tx.execute(
            """
            INSERT INTO websocket_connection (http_request_id) VALUES (%s) RETURNING id
            """,
            (http_request_id,),
        )
        return tx.fetchone()[0]
