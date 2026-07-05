
from dataclasses import dataclass

from psycopg import Cursor

from ctf_proxy.db.connection import Row


@dataclass
class TcpConnectionRow:
    id: int
    port: int
    connection_id: int
    start_time: int
    duration_ms: int
    bytes_in: int
    bytes_out: int
    is_blocked: bool
    tap_id: str | None
    batch_id: str | None

    @dataclass
    class Insert:
        port: int
        connection_id: int
        start_time: int
        duration_ms: int
        bytes_in: int
        bytes_out: int
        is_blocked: bool = 0
        tap_id: str | None = None
        batch_id: str | None = None


class TcpConnectionTable:
    def insert(self, tx: Cursor, **kwargs) -> int:
        row = (
            TcpConnectionRow.Insert(**kwargs)
            if not isinstance(kwargs.get("port"), TcpConnectionRow.Insert)
            else kwargs["port"]
        )
        if isinstance(kwargs.get("port"), TcpConnectionRow.Insert):
            row = kwargs["port"]
        else:
            row = TcpConnectionRow.Insert(**kwargs)

        tx.execute(
            """
            INSERT INTO tcp_connection (
                port, connection_id, start_time, duration_ms,
                bytes_in, bytes_out, is_blocked, tap_id, batch_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (
                row.port,
                row.connection_id,
                row.start_time,
                row.duration_ms,
                row.bytes_in,
                row.bytes_out,
                int(row.is_blocked),
                row.tap_id,
                row.batch_id,
            ),
        )
        return tx.fetchone()[0]

    def read_after(self, tx: Cursor, last_id: int, limit: int) -> list[Row]:
        return tx.execute(
            "SELECT * FROM tcp_connection WHERE id > %s ORDER BY id LIMIT %s",
            (last_id, limit),
        ).fetchall()

    def read_range(
        self,
        tx: Cursor,
        last_id: int,
        target_id: int,
        ports: list[int] | None,
        limit: int,
    ) -> list[Row]:
        params: list[int] = [last_id, target_id]
        port_clause = ""
        if ports:
            placeholders = ",".join(["%s"] * len(ports))
            port_clause = f" AND port IN ({placeholders})"
            params.extend(ports)
        params.append(limit)
        return tx.execute(
            f"SELECT * FROM tcp_connection WHERE id > %s AND id <= %s{port_clause} ORDER BY id LIMIT %s",
            params,
        ).fetchall()

    def read_by_ids(self, tx: Cursor, ids: list[int]) -> list[Row]:
        placeholders = ",".join(["%s"] * len(ids))
        return tx.execute(
            f"SELECT * FROM tcp_connection WHERE id IN ({placeholders}) ORDER BY id",
            ids,
        ).fetchall()
