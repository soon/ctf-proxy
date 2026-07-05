from psycopg import Cursor


class TcpConnectionTimeStatsTable:
    def increment(
        self,
        tx: Cursor,
        port: int,
        read_min: int,
        read_max: int,
        write_min: int,
        write_max: int,
        time: int,
    ) -> None:
        tx.execute(
            """
            INSERT INTO tcp_connection_time_stats (port, read_min, read_max, write_min, write_max, time, count)
            VALUES (%s, %s, %s, %s, %s, %s, 1)
            ON CONFLICT(port, read_min, read_max, write_min, write_max, time)
            DO UPDATE SET count = count + 1
        """,
            (port, read_min, read_max, write_min, write_max, time),
        )
