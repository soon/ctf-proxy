from dataclasses import dataclass

from psycopg import Cursor

from ctf_proxy.db.base import (
    RowStatus,
    TimeStatsIncrementRow,
    TimeStatsInsertRow,
    TimeStatsRow,
)


@dataclass
class HttpRequestTimeStatsRow(TimeStatsRow):
    blocked_count: int

    @dataclass
    class Insert(TimeStatsInsertRow):
        blocked_count: int

    @dataclass
    class Increment(TimeStatsIncrementRow):
        blocked_count: int


class HttpRequestTimeStatsTable:
    def insert(self, tx: Cursor, row: HttpRequestTimeStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO http_request_time_stats (port, time, count, blocked_count)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (row.port, row.time, row.count, row.blocked_count),
        )
        return tx.fetchone()[0]

    def increment(
        self, tx: Cursor, increments: HttpRequestTimeStatsRow.Increment
    ) -> RowStatus:
        sql = """
          UPDATE http_request_time_stats SET
              count = count + %s,
              blocked_count = blocked_count + %s
          WHERE port = %s AND time = %s;
        """
        params = (
            increments.count,
            increments.blocked_count,
            increments.port,
            increments.time,
        )
        tx.execute(sql, params)

        if not tx.rowcount:
            self.insert(
                tx,
                HttpRequestTimeStatsRow.Insert(
                    port=increments.port,
                    time=increments.time,
                    count=increments.count,
                    blocked_count=increments.blocked_count,
                ),
            )
            return RowStatus.NEW

        return RowStatus.UPDATED
