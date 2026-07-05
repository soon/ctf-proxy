from dataclasses import dataclass

from psycopg import Cursor

from ctf_proxy.db.base import RowStatus


@dataclass
class TcpConnectionStatsRow:
    id: int
    port: int
    read_min: int
    read_max: int
    write_min: int
    write_max: int
    count: int

    @dataclass
    class Insert:
        port: int
        read_min: int
        read_max: int
        write_min: int
        write_max: int
        count: int = 1

    @dataclass
    class Increment:
        port: int
        read_min: int
        read_max: int
        write_min: int
        write_max: int
        count: int = 1


class TcpConnectionStatsTable:
    def increment(self, tx: Cursor, row: TcpConnectionStatsRow.Increment) -> RowStatus:
        # Try to update existing record
        tx.execute(
            """
            UPDATE tcp_connection_stats
            SET count = count + %s
            WHERE port = %s AND read_min = %s AND read_max = %s AND write_min = %s AND write_max = %s
        """,
            (row.count, row.port, row.read_min, row.read_max, row.write_min, row.write_max),
        )

        if tx.rowcount == 0:
            # Insert new record if not exists
            tx.execute(
                """
                INSERT INTO tcp_connection_stats (port, read_min, read_max, write_min, write_max, count)
                VALUES (%s, %s, %s, %s, %s, %s)
            """,
                (row.port, row.read_min, row.read_max, row.write_min, row.write_max, row.count),
            )
            return RowStatus.NEW

        return RowStatus.UPDATED
