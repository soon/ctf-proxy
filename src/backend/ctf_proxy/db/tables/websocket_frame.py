from dataclasses import dataclass
from typing import ClassVar

from psycopg import Cursor

from ctf_proxy.db.connection import nul_safe
from ctf_proxy.db.refs import Ref


@dataclass
class WebSocketFrameRow:
    id: int
    connection_id: int
    timestamp: int
    direction: str
    opcode: str
    payload: bytes | None
    payload_text: str | None
    payload_size: int
    masked: bool

    @dataclass
    class Insert:
        TABLE: ClassVar[str] = "websocket_frame"
        connection_id: "int | Ref"
        ord: int
        opcode: str
        payload: bytes
        payload_text: str
        payload_size: int
        is_client: int


class WebSocketFrameTable:
    def insert_many(self, tx: Cursor, frames: list[WebSocketFrameRow.Insert]) -> None:
        tx.executemany(
            """
            INSERT INTO websocket_frame (
                connection_id, ord, opcode, payload, payload_text,
                payload_size, is_client
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    frame.connection_id,
                    frame.ord,
                    frame.opcode,
                    frame.payload,
                    nul_safe(frame.payload_text),
                    frame.payload_size,
                    int(bool(frame.is_client)),
                )
                for frame in frames
            ],
        )
