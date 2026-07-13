from dataclasses import dataclass
from typing import ClassVar

from psycopg import Cursor

from ctf_proxy.db.connection import nul_safe
from ctf_proxy.db.refs import Ref


@dataclass
class FlagRow:
    id: int
    http_request_id: int | None
    http_response_id: int | None
    tcp_connection_id: int | None
    tcp_event_id: int | None
    websocket_connection_id: int | None
    websocket_frame_id: int | None
    location: str | None
    offset: int | None
    value: str

    @dataclass
    class Insert:
        TABLE: ClassVar[str] = "flag"
        value: str
        http_request_id: "int | None | Ref" = None
        http_response_id: "int | None | Ref" = None
        tcp_connection_id: "int | None | Ref" = None
        tcp_event_id: "int | None | Ref" = None
        websocket_connection_id: "int | None | Ref" = None
        websocket_frame_id: "int | None | Ref" = None
        location: str | None = None
        offset: int | None = None


class FlagTable:
    def insert(self, tx: Cursor, **kwargs) -> int:
        row = FlagRow.Insert(**kwargs)
        tx.execute(
            """
            INSERT INTO flag (http_request_id, http_response_id, tcp_connection_id, tcp_event_id, websocket_connection_id, websocket_frame_id, location, "offset", value)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (
                row.http_request_id,
                row.http_response_id,
                row.tcp_connection_id,
                row.tcp_event_id,
                row.websocket_connection_id,
                row.websocket_frame_id,
                row.location,
                row.offset,
                nul_safe(row.value),
            ),
        )
        return tx.fetchone()[0]

    def insert_many(self, tx: Cursor, flags: list[FlagRow.Insert]) -> None:
        tx.executemany(
            """
            INSERT INTO flag (http_request_id, http_response_id, tcp_connection_id, tcp_event_id, websocket_connection_id, websocket_frame_id, location, "offset", value)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    f.http_request_id,
                    f.http_response_id,
                    f.tcp_connection_id,
                    f.tcp_event_id,
                    f.websocket_connection_id,
                    f.websocket_frame_id,
                    f.location,
                    f.offset,
                    nul_safe(f.value),
                )
                for f in flags
            ],
        )
