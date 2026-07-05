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
                total_connections = total_connections + 1,
                total_bytes_in = total_bytes_in + %s,
                total_bytes_out = total_bytes_out + %s,
                avg_duration_ms = CAST((avg_duration_ms * (total_connections - 1) + %s) AS INTEGER) / total_connections,
                total_flags_found = total_flags_found + %s
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
