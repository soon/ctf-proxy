from dataclasses import dataclass
from datetime import datetime

from psycopg import Cursor


@dataclass
class AlertRow:
    id: int
    created: datetime
    port: int
    description: str
    http_request_id: int | None = None
    http_response_id: int | None = None

    @dataclass
    class Insert:
        port: int
        created: int
        description: str
        http_request_id: int | None = None
        http_response_id: int | None = None
        tcp_connection_id: int | None = None


class AlertTable:
    def insert(
        self,
        tx: Cursor,
        row: AlertRow.Insert,
    ) -> None:
        tx.execute(
            """
            INSERT INTO alert (created, port, http_request_id, http_response_id, tcp_connection_id, description)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                row.created,
                row.port,
                row.http_request_id,
                row.http_response_id,
                row.tcp_connection_id,
                row.description,
            ),
        )
