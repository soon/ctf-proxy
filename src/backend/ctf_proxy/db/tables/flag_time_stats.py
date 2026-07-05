from dataclasses import dataclass

from psycopg import Cursor

from ctf_proxy.db.base import RowStatus


@dataclass
class FlagTimeStatsRow:
    id: int
    port: int
    time: int
    write_count: int
    read_count: int

    @dataclass
    class Insert:
        port: int
        time: int
        write_count: int
        read_count: int

    @dataclass
    class Increment:
        port: int
        time: int
        write_count: int
        read_count: int


class FlagTimeStatsTable:
    def insert(self, tx: Cursor, row: FlagTimeStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO flag_time_stats (port, time, write_count, read_count)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (row.port, row.time, row.write_count, row.read_count),
        )
        return tx.fetchone()[0]

    def increment(self, tx: Cursor, increments: FlagTimeStatsRow.Increment) -> RowStatus:
        sql = """
          UPDATE flag_time_stats SET
              write_count = write_count + %s,
              read_count = read_count + %s
          WHERE port = %s AND time = %s;
        """
        params = (
            increments.write_count,
            increments.read_count,
            increments.port,
            increments.time,
        )
        tx.execute(sql, params)

        if not tx.rowcount:
            self.insert(
                tx,
                FlagTimeStatsRow.Insert(
                    port=increments.port,
                    time=increments.time,
                    write_count=increments.write_count,
                    read_count=increments.read_count,
                ),
            )
            return RowStatus.NEW

        return RowStatus.UPDATED
