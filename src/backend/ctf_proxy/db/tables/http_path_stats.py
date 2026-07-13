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
        tx.execute(
            """
            INSERT INTO http_path_stats (port, path, count)
            VALUES (%s, %s, %s)
            ON CONFLICT (port, path) DO UPDATE SET count = http_path_stats.count + EXCLUDED.count
            RETURNING (xmax = 0) AS inserted
            """,
            (increments.port, increments.path, increments.count),
        )
        inserted = tx.fetchone()[0]
        return RowStatus.NEW if inserted else RowStatus.UPDATED
