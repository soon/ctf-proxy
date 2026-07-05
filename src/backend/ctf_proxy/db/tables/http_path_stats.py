from dataclasses import dataclass

from psycopg import Cursor

from ctf_proxy.db.base import RowStatus


@dataclass
class HttpPathStatsRow:
    id: int
    port: int
    path: str
    count: int

    @dataclass
    class Insert:
        port: int
        path: str
        count: int = 0

    @dataclass
    class Increment:
        port: int
        path: str
        count: int = 0


class HttpPathStatsTable:
    def insert(self, tx: Cursor, row: HttpPathStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO http_path_stats (port, path, count)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (row.port, row.path, row.count),
        )
        return tx.fetchone()[0]

    def increment(self, tx: Cursor, increments: HttpPathStatsRow.Increment) -> RowStatus:
        sql = """
UPDATE http_path_stats SET
    count = count + %s
WHERE port = %s AND path = %s;
"""
        params = (
            increments.count,
            increments.port,
            increments.path,
        )
        tx.execute(sql, params)

        if not tx.rowcount:
            self.insert(
                tx,
                HttpPathStatsRow.Insert(
                    port=increments.port, path=increments.path, count=increments.count
                ),
            )
            return RowStatus.NEW

        return RowStatus.UPDATED
