from dataclasses import dataclass

from psycopg import Cursor


@dataclass
class ServiceStatsRow:
    id: int
    port: int
    total_requests: int
    total_blocked_requests: int
    total_responses: int
    total_blocked_responses: int
    total_flags_written: int
    total_flags_retrieved: int
    total_flags_blocked: int
    total_websocket_connections: int
    total_websocket_frames: int

    @dataclass
    class Insert:
        port: int

    @dataclass
    class Increment:
        port: int
        total_requests: int = 0
        total_blocked_requests: int = 0
        total_responses: int = 0
        total_blocked_responses: int = 0
        total_flags_written: int = 0
        total_flags_retrieved: int = 0
        total_flags_blocked: int = 0
        total_tcp_connections: int = 0
        total_tcp_bytes_in: int = 0
        total_tcp_bytes_out: int = 0
        total_websocket_connections: int = 0
        total_websocket_frames: int = 0


class ServiceStatsTable:
    def insert(self, tx: Cursor, row: ServiceStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO service_stats (port)
            VALUES (%s) RETURNING id
            """,
            (row.port,),
        )
        return tx.fetchone()[0]

    def increment(self, tx: Cursor, increments: ServiceStatsRow.Increment) -> None:
        sql = """
UPDATE service_stats SET
    total_requests = total_requests + %s,
    total_blocked_requests = total_blocked_requests + %s,
    total_responses = total_responses + %s,
    total_blocked_responses = total_blocked_responses + %s,
    total_flags_written = total_flags_written + %s,
    total_flags_retrieved = total_flags_retrieved + %s,
    total_flags_blocked = total_flags_blocked + %s,
    total_websocket_connections = total_websocket_connections + %s,
    total_websocket_frames = total_websocket_frames + %s
WHERE port = %s;
"""
        params = (
            increments.total_requests,
            increments.total_blocked_requests,
            increments.total_responses,
            increments.total_blocked_responses,
            increments.total_flags_written,
            increments.total_flags_retrieved,
            increments.total_flags_blocked,
            increments.total_websocket_connections,
            increments.total_websocket_frames,
            increments.port,
        )
        tx.execute(sql, params)
        if not tx.rowcount:
            self.insert(tx, ServiceStatsRow.Insert(port=increments.port))
            tx.execute(sql, params)
            assert tx.rowcount, "Failed to increment service stats after insert"

    def get_by_ports(self, tx: Cursor, ports: list[int]) -> list[ServiceStatsRow]:
        if not ports:
            return []

        placeholders = ",".join("%s" for _ in ports)
        fields = [
            "port",
            "total_requests",
            "total_blocked_requests",
            "total_responses",
            "total_blocked_responses",
            "total_flags_written",
            "total_flags_retrieved",
            "total_flags_blocked",
            "total_websocket_connections",
            "total_websocket_frames",
        ]
        sql = f"SELECT {', '.join(fields)} FROM service_stats WHERE port IN ({placeholders})"
        tx.execute(sql, ports)
        rows = tx.fetchall()
        return [ServiceStatsRow(**dict(zip(fields, row, strict=False))) for row in rows]
