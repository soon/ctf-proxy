from psycopg import Cursor


class TcpStatsTable:
    def increment(
        self,
        tx: Cursor,
        port: int,
        bytes_in: int,
        bytes_out: int,
        duration_ms: int,
        total_flags_found: int,
    ) -> None:
        tx.execute(
            """
            INSERT INTO tcp_stats (port, total_connections, total_bytes_in, total_bytes_out, avg_duration_ms, total_flags_found)
            VALUES (%s, 1, %s, %s, %s, %s)
            ON CONFLICT(port)
            DO UPDATE SET
                total_connections = tcp_stats.total_connections + 1,
                total_bytes_in = tcp_stats.total_bytes_in + %s,
                total_bytes_out = tcp_stats.total_bytes_out + %s,
                avg_duration_ms = CAST((tcp_stats.avg_duration_ms * (tcp_stats.total_connections - 1) + %s) AS INTEGER) / tcp_stats.total_connections,
                total_flags_found = tcp_stats.total_flags_found + %s
        """,
            (
                port,
                bytes_in,
                bytes_out,
                duration_ms,
                total_flags_found,
                bytes_in,
                bytes_out,
                duration_ms,
                total_flags_found,
            ),
        )
