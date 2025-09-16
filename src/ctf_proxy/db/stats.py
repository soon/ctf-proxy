import sqlite3
from dataclasses import dataclass

from ctf_proxy.db.base import RowStatus, TimeStatsIncrementRow, TimeStatsInsertRow, TimeStatsRow


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


class HttpPathTimeStatsTable:
    def insert(self, tx: sqlite3.Cursor, row: HttpPathTimeStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO http_path_time_stats (port, method, path, time, count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (row.port, row.method, row.path, row.time, row.count),
        )
        return tx.lastrowid

    def increment(
        self, tx: sqlite3.Cursor, increments: HttpPathTimeStatsRow.Increment
    ) -> RowStatus:
        sql = """
          UPDATE http_path_time_stats SET
              count = count + ?
          WHERE port = ? AND method = ? AND path = ? AND time = ?;
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


class HttpQueryParamTimeStatsTable:
    def insert(self, tx: sqlite3.Cursor, row: HttpQueryParamTimeStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO http_query_param_time_stats (port, param, value, time, count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (row.port, row.param, row.value, row.time, row.count),
        )
        return tx.lastrowid

    def increment(
        self, tx: sqlite3.Cursor, increments: HttpQueryParamTimeStatsRow.Increment
    ) -> RowStatus:
        sql = """
          UPDATE http_query_param_time_stats SET
              count = count + ?
          WHERE port = ? AND param = ? AND value = ? AND time = ?;
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


class HttpHeaderTimeStatsTable:
    def insert(self, tx: sqlite3.Cursor, row: HttpHeaderTimeStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO http_header_time_stats (port, name, value, time, count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (row.port, row.name, row.value, row.time, row.count),
        )
        return tx.lastrowid

    def increment(
        self, tx: sqlite3.Cursor, increments: HttpHeaderTimeStatsRow.Increment
    ) -> RowStatus:
        sql = """
          UPDATE http_header_time_stats SET
              count = count + ?
          WHERE port = ? AND name = ? AND value = ? AND time = ?;
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
