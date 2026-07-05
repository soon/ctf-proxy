from dataclasses import dataclass

from psycopg import Cursor

from ctf_proxy.db.base import (
    RowStatus,
    TimeStatsIncrementRow,
    TimeStatsInsertRow,
    TimeStatsRow,
)


@dataclass
class HttpQueryParamTimeStatsRow(TimeStatsRow):
    param: str
    value: str

    @dataclass
    class Insert(TimeStatsInsertRow):
        param: str
        value: str

    @dataclass
    class Increment(TimeStatsIncrementRow):
        param: str
        value: str


class HttpQueryParamTimeStatsTable:
    def insert(self, tx: Cursor, row: HttpQueryParamTimeStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO http_query_param_time_stats (port, param, value, time, count)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (row.port, row.param, row.value, row.time, row.count),
        )
        return tx.fetchone()[0]

    def increment(
        self, tx: Cursor, increments: HttpQueryParamTimeStatsRow.Increment
    ) -> RowStatus:
        sql = """
          UPDATE http_query_param_time_stats SET
              count = count + %s
          WHERE port = %s AND param = %s AND value = %s AND time = %s;
        """
        params = (
            increments.count,
            increments.port,
            increments.param,
            increments.value,
            increments.time,
        )
        tx.execute(sql, params)

        if not tx.rowcount:
            self.insert(
                tx,
                HttpQueryParamTimeStatsRow.Insert(
                    port=increments.port,
                    param=increments.param,
                    value=increments.value,
                    time=increments.time,
                    count=increments.count,
                ),
            )
            return RowStatus.NEW

        return RowStatus.UPDATED
