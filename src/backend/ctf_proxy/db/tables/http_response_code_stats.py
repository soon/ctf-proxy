from dataclasses import dataclass

from psycopg import Cursor


@dataclass
class HttpResponseCodeStatsRow:
    id: int
    port: int
    status_code: int
    count: int

    @dataclass
    class Insert:
        port: int
        status_code: int
        count: int = 0

    @dataclass
    class Increment:
        port: int
        status_code: int
        count: int = 0


class HttpResponseCodeStatsTable:
    def insert(self, tx: Cursor, row: HttpResponseCodeStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO http_response_code_stats (port, status_code, count)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (row.port, row.status_code, row.count),
        )
        return tx.fetchone()[0]

    def increment(self, tx: Cursor, increments: HttpResponseCodeStatsRow.Increment) -> None:
        sql = """
UPDATE http_response_code_stats SET
    count = count + %s
WHERE port = %s AND status_code = %s;
"""
        params = (
            increments.count,
            increments.port,
            increments.status_code,
        )
        tx.execute(sql, params)
        if not tx.rowcount:
            self.insert(
                tx,
                HttpResponseCodeStatsRow.Insert(
                    port=increments.port, status_code=increments.status_code, count=increments.count
                ),
            )

    def get_by_ports(self, tx: Cursor, ports: list[int]) -> list[HttpResponseCodeStatsRow]:
        if not ports:
            return []

        placeholders = ",".join("%s" for _ in ports)
        fields = [
            "port",
            "status_code",
            "count",
        ]
        sql = f"SELECT {', '.join(fields)} FROM http_response_code_stats WHERE port IN ({placeholders})"
        tx.execute(sql, ports)
        rows = tx.fetchall()
        return [HttpResponseCodeStatsRow(**dict(zip(fields, row, strict=False))) for row in rows]
