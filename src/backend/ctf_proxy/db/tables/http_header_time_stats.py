from dataclasses import dataclass

from psycopg import Cursor

from ctf_proxy.db.base import (
    RowStatus,
    TimeStatsIncrementRow,
    TimeStatsInsertRow,
    TimeStatsRow,
)


@dataclass
class HttpHeaderTimeStatsRow(TimeStatsRow):
    name: str
    value: str

    @dataclass
    class Insert(TimeStatsInsertRow):
        name: str
        value: str

    @dataclass
    class Increment(TimeStatsIncrementRow):
        name: str
        value: str


class HttpHeaderTimeStatsTable:
    def insert(self, tx: Cursor, row: HttpHeaderTimeStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO http_header_time_stats (port, name, value, time, count)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (row.port, row.name, row.value, row.time, row.count),
        )
        return tx.fetchone()[0]

    def increment(
        self, tx: Cursor, increments: HttpHeaderTimeStatsRow.Increment
    ) -> RowStatus:
        sql = """
          UPDATE http_header_time_stats SET
              count = count + %s
          WHERE port = %s AND name = %s AND value = %s AND time = %s;
        """
        params = (
            increments.count,
            increments.port,
            increments.name,
            increments.value,
            increments.time,
        )
        tx.execute(sql, params)

        if not tx.rowcount:
            self.insert(
                tx,
                HttpHeaderTimeStatsRow.Insert(
                    port=increments.port,
                    name=increments.name,
                    value=increments.value,
                    time=increments.time,
                    count=increments.count,
                ),
            )
            return RowStatus.NEW

        return RowStatus.UPDATED
