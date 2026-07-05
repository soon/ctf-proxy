from dataclasses import dataclass

from psycopg import Cursor

from ctf_proxy.db.base import (
    RowStatus,
    TimeStatsIncrementRow,
    TimeStatsInsertRow,
    TimeStatsRow,
)


@dataclass
class HttpPathTimeStatsRow(TimeStatsRow):
    method: str
    path: str

    @dataclass
    class Insert(TimeStatsInsertRow):
        method: str
        path: str

    @dataclass
    class Increment(TimeStatsIncrementRow):
        method: str
        path: str


class HttpPathTimeStatsTable:
    def insert(self, tx: Cursor, row: HttpPathTimeStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO http_path_time_stats (port, method, path, time, count)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (row.port, row.method, row.path, row.time, row.count),
        )
        return tx.fetchone()[0]

    def increment(
        self, tx: Cursor, increments: HttpPathTimeStatsRow.Increment
    ) -> RowStatus:
        sql = """
          UPDATE http_path_time_stats SET
              count = count + %s
          WHERE port = %s AND method = %s AND path = %s AND time = %s;
        """
        params = (
            increments.count,
            increments.port,
            increments.method,
            increments.path,
            increments.time,
        )
        tx.execute(sql, params)

        if not tx.rowcount:
            self.insert(
                tx,
                HttpPathTimeStatsRow.Insert(
                    port=increments.port,
                    method=increments.method,
                    path=increments.path,
                    time=increments.time,
                    count=increments.count,
                ),
            )
            return RowStatus.NEW

        return RowStatus.UPDATED
