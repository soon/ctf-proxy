#!/usr/bin/env python3

import enum
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class HttpRequestRow:
    id: int
    port: int
    start_time: datetime
    path: str
    method: str
    user_agent: str | None
    body: str | None
    tap_id: str | None
    batch_id: str | None


@dataclass
class HttpResponseRow:
    id: int
    request_id: int
    status: int
    body: str | None


@dataclass
class HttpHeaderRow:
    id: int
    name: str
    value: str
    request_id: int | None = None
    response_id: int | None = None

    @dataclass
    class Insert:
        name: str
        value: str
        request_id: int | None = None
        response_id: int | None = None


@dataclass
class AlertRow:
    id: int
    created: datetime
    port: int
    description: str
    http_request_id: int | None = None
    http_response_id: int | None = None

    @dataclass
    class Insert:
        port: int
        created: int
        description: str
        http_request_id: int | None = None
        http_response_id: int | None = None


@dataclass
class FlagRow:
    id: int
    value: str
    http_request_id: int | None
    http_response_id: int | None
    location: str | None
    offset: int | None

    @dataclass
    class Insert:
        value: str
        http_request_id: int | None = None
        http_response_id: int | None = None
        location: str | None = None
        offset: int | None = None


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


class RowStatus(enum.Enum):
    NEW = "new"
    UPDATED = "updated"


class BaseTable:
    def __init__(self, db_file: str):
        self.db_file = db_file

    def get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_file)


class HttpRequestTable(BaseTable):
    def insert(
        self,
        tx: sqlite3.Cursor,
        port: int,
        start_time: int,
        path: str,
        method: str,
        user_agent: str | None = None,
        body: str | None = None,
        is_blocked: bool | None = False,
        tap_id: str | None = None,
        batch_id: str | None = None,
    ) -> int:
        tx.execute(
            """
            INSERT INTO http_request (port, start_time, path, method, user_agent, body, is_blocked, tap_id, batch_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (port, start_time, path, method, user_agent, body, is_blocked, tap_id, batch_id),
        )
        return tx.lastrowid

    def get_by_id(self, request_id: int) -> HttpRequestRow | None:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM http_request WHERE id = ?", (request_id,))
            row = cursor.fetchone()
            if row:
                return HttpRequestRow(**dict(row))
            return None

    def get_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM http_request")
            return cursor.fetchone()[0]


class HttpResponseTable(BaseTable):
    def insert(
        self, tx: sqlite3.Cursor, request_id: int, status: int, body: str | None = None
    ) -> int:
        tx.execute(
            """
            INSERT INTO http_response (request_id, status, body)
            VALUES (?, ?, ?)
            """,
            (request_id, status, body),
        )
        return tx.lastrowid

    def get_by_request_id(self, request_id: int) -> HttpResponseRow | None:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM http_response WHERE request_id = ?", (request_id,))
            row = cursor.fetchone()
            if row:
                return HttpResponseRow(**dict(row))
            return None


class HttpHeaderTable(BaseTable):
    def insert_many(self, tx: sqlite3.Cursor, headers: list[HttpHeaderRow.Insert]) -> None:
        tx.executemany(
            """
            INSERT INTO http_header (request_id, response_id, name, value)
            VALUES (?, ?, ?, ?)
            """,
            [(h.request_id, h.response_id, h.name, h.value) for h in headers],
        )

    def get_by_request_id(self, request_id: int) -> list[HttpHeaderRow]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM http_header WHERE request_id = ?", (request_id,))
            rows = cursor.fetchall()
            return [HttpHeaderRow(**dict(row)) for row in rows]

    def get_by_response_id(self, response_id: int) -> list[HttpHeaderRow]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM http_header WHERE response_id = ?", (response_id,))
            rows = cursor.fetchall()
            return [HttpHeaderRow(**dict(row)) for row in rows]


class AlertTable(BaseTable):
    def insert(
        self,
        tx: sqlite3.Cursor,
        row: AlertRow.Insert,
    ) -> None:
        tx.execute(
            """
            INSERT INTO alert (created, port, http_request_id, http_response_id, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (row.created, row.port, row.http_request_id, row.http_response_id, row.description),
        )


class FlagTable(BaseTable):
    def insert_many(self, tx: sqlite3.Cursor, flags: list[FlagRow.Insert]) -> None:
        tx.executemany(
            """
            INSERT INTO flag (http_request_id, http_response_id, location, offset, value)
            VALUES (?, ?, ?, ?, ?)
            """,
            [(f.http_request_id, f.http_response_id, f.location, f.offset, f.value) for f in flags],
        )

    def get_by_request_id(self, request_id: int) -> list[FlagRow]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM flag WHERE http_request_id = ? ORDER BY created DESC", (request_id,)
            )
            rows = cursor.fetchall()
            return [FlagRow(**dict(row)) for row in rows]

    def get_by_response_id(self, response_id: int) -> list[FlagRow]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM flag WHERE http_response_id = ? ORDER BY created DESC",
                (response_id,),
            )
            rows = cursor.fetchall()
            return [FlagRow(**dict(row)) for row in rows]

    def get_all(self, limit: int = 100) -> list[FlagRow]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM flag ORDER BY created DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [FlagRow(**dict(row)) for row in rows]


class ServiceStatsTable(BaseTable):
    def insert(self, tx: sqlite3.Cursor, row: ServiceStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO service_stats (port)
            VALUES (?)
            """,
            (row.port,),
        )
        return tx.lastrowid

    def increment(self, tx: sqlite3.Cursor, increments: ServiceStatsRow.Increment) -> None:
        sql = """
UPDATE service_stats SET
    total_requests = total_requests + ?,
    total_blocked_requests = total_blocked_requests + ?,
    total_responses = total_responses + ?,
    total_blocked_responses = total_blocked_responses + ?,
    total_flags_written = total_flags_written + ?,
    total_flags_retrieved = total_flags_retrieved + ?,
    total_flags_blocked = total_flags_blocked + ?
WHERE port = ?;
"""
        params = (
            increments.total_requests,
            increments.total_blocked_requests,
            increments.total_responses,
            increments.total_blocked_responses,
            increments.total_flags_written,
            increments.total_flags_retrieved,
            increments.total_flags_blocked,
            increments.port,
        )
        tx.execute(sql, params)
        if not tx.rowcount:
            self.insert(tx, ServiceStatsRow.Insert(port=increments.port))
            tx.execute(sql, params)
            assert tx.rowcount, "Failed to increment service stats after insert"

    def get_by_ports(self, tx: sqlite3.Cursor, ports: list[int]) -> list[ServiceStatsRow]:
        if not ports:
            return []

        placeholders = ",".join("?" for _ in ports)
        fields = [
            "port",
            "total_requests",
            "total_blocked_requests",
            "total_responses",
            "total_blocked_responses",
            "total_flags_written",
            "total_flags_retrieved",
            "total_flags_blocked",
        ]
        sql = f"SELECT {', '.join(fields)} FROM service_stats WHERE port IN ({placeholders})"
        tx.execute(sql, ports)
        rows = tx.fetchall()
        return [ServiceStatsRow(**dict(zip(fields, row, strict=False))) for row in rows]


class HttpResponseCodeStatsTable(BaseTable):
    def insert(self, tx: sqlite3.Cursor, row: HttpResponseCodeStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO http_response_code_stats (port, status_code, count)
            VALUES (?, ?, ?)
            """,
            (row.port, row.status_code, row.count),
        )
        return tx.lastrowid

    def increment(self, tx: sqlite3.Cursor, increments: HttpResponseCodeStatsRow.Increment) -> None:
        sql = """
UPDATE http_response_code_stats SET
    count = count + ?
WHERE port = ? AND status_code = ?;
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

    def get_by_ports(self, tx: sqlite3.Cursor, ports: list[int]) -> list[HttpResponseCodeStatsRow]:
        if not ports:
            return []

        placeholders = ",".join("?" for _ in ports)
        fields = [
            "port",
            "status_code",
            "count",
        ]
        sql = f"SELECT {', '.join(fields)} FROM http_response_code_stats WHERE port IN ({placeholders})"
        tx.execute(sql, ports)
        rows = tx.fetchall()
        return [HttpResponseCodeStatsRow(**dict(zip(fields, row, strict=False))) for row in rows]


class HttpPathStatsTable(BaseTable):
    def insert(self, tx: sqlite3.Cursor, row: HttpPathStatsRow.Insert) -> int:
        tx.execute(
            """
            INSERT INTO http_path_stats (port, path, count)
            VALUES (?, ?, ?)
            """,
            (row.port, row.path, row.count),
        )
        return tx.lastrowid

    def increment(self, tx: sqlite3.Cursor, increments: HttpPathStatsRow.Increment) -> RowStatus:
        sql = """
UPDATE http_path_stats SET
    count = count + ?
WHERE port = ? AND path = ?;
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


def make_db(path: str = "proxy_stats.db"):
    db = ProxyStatsDB(path)
    db.init_db()
    return db


class ProxyStatsDB:
    def __init__(self, db_file="proxy_stats.db"):
        self.db_file = db_file
        self.http_requests = HttpRequestTable(db_file)
        self.http_responses = HttpResponseTable(db_file)
        self.http_headers = HttpHeaderTable(db_file)
        self.alerts = AlertTable(db_file)
        self.flags = FlagTable(db_file)
        self.service_stats = ServiceStatsTable(db_file)
        self.http_response_code_stats = HttpResponseCodeStatsTable(db_file)
        self.http_path_stats = HttpPathStatsTable(db_file)
        # self.conn = sqlite3.connect(self.db_file)

    # def transaction(self):
    #     return closing(self.conn.cursor())

    def connect(self):
        return sqlite3.connect(self.db_file)

    def init_schema(self, schema_file: str = None) -> None:
        if schema_file is None:
            schema_file = os.path.join(os.path.dirname(__file__), "schema.sql")

        if not os.path.exists(schema_file):
            logger.error(f"Schema file not found: {schema_file}")
            return

        with open(schema_file) as f:
            schema_sql = f.read()

        with sqlite3.connect(self.db_file) as conn:
            conn.executescript(schema_sql)

        logger.info(f"Database schema initialized from {schema_file}")

    def init_db(self) -> None:
        self.init_schema()
        logger.info(f"Database initialized: {self.db_file}")

    def get_stats(self):
        total_requests = self.http_requests.get_count()

        return {
            "total_requests": total_requests,
        }
