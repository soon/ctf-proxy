from dataclasses import dataclass

from psycopg import Cursor

from ctf_proxy.db.connection import nul_safe


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
        connection_id: int
        order: int
        opcode: str
        payload: bytes
        payload_text: str
        payload_size: int
        is_client: bool


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
                    frame.order,
                    frame.opcode,
                    frame.payload,
                    nul_safe(frame.payload_text),
                    frame.payload_size,
                    int(bool(frame.is_client)),
                )
                for frame in frames
            ],
        )
