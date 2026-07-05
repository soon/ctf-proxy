
from dataclasses import dataclass

from psycopg import Cursor

from ctf_proxy.db.connection import Row, nul_safe


@dataclass
class TcpEventRow:
    id: int
    connection_id: int
    timestamp: int
    event_type: str
    data: bytes | None
    data_text: str | None
    data_size: int
    end_stream: int
    truncated: int

    @dataclass
    class Insert:
        connection_id: int
        timestamp: int
        event_type: str
        data: bytes | None = None
        data_text: str | None = None
        data_size: int = 0
        end_stream: bool = False
        truncated: bool = False


class TcpEventTable:
    def insert(self, tx: Cursor, **kwargs) -> int:
        row = TcpEventRow.Insert(**kwargs)

        tx.execute(
            """
            INSERT INTO tcp_event (
                connection_id, timestamp, event_type, data, data_text,
                data_size, end_stream, truncated
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (
                row.connection_id,
                row.timestamp,
                row.event_type,
                row.data,
                nul_safe(row.data_text),
                row.data_size,
                int(row.end_stream),
                int(row.truncated),
            ),
        )
        return tx.fetchone()[0]

    def get_by_connection_ids(
        self, tx: Cursor, connection_ids: list[int]
    ) -> list[Row]:
        placeholders = ",".join(["%s"] * len(connection_ids))
        return tx.execute(
            "SELECT connection_id, event_type, data_text, data_size, end_stream, truncated "
            f"FROM tcp_event WHERE connection_id IN ({placeholders}) ORDER BY id",
            connection_ids,
        ).fetchall()
