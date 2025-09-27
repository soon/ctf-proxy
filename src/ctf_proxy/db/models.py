#!/usr/bin/env python3

import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from ctf_proxy.db.base import RowStatus
from ctf_proxy.db.stats import (
    FlagTimeStatsTable,
    HttpHeaderTimeStatsTable,
    HttpPathTimeStatsTable,
    HttpQueryParamTimeStatsTable,
    HttpRequestTimeStatsTable,
)

logger = logging.getLogger(__name__)


@dataclass
class SqlExecutionResult:
    rows: list[dict]
    columns: list[str]
    query_time_ms: float


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
        tcp_connection_id: int | None = None


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
        tcp_connection_id: int | None = None
        tcp_event_id: int | None = None
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
        total_tcp_connections: int = 0
        total_tcp_bytes_in: int = 0
        total_tcp_bytes_out: int = 0


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


@dataclass
class SessionRow:
    id: int
    port: int
    key: str


@dataclass
class TcpConnectionRow:
    id: int
    port: int
    connection_id: int
    start_time: int
    duration_ms: int
    bytes_in: int
    bytes_out: int
    is_blocked: bool
    tap_id: str | None
    batch_id: str | None

    @dataclass
    class Insert:
        port: int
        connection_id: int
        start_time: int
        duration_ms: int
        bytes_in: int
        bytes_out: int
        is_blocked: bool = 0
        tap_id: str | None = None
        batch_id: str | None = None


@dataclass
class TcpConnectionStatsRow:
    id: int
    port: int
    read_min: int
    read_max: int
    write_min: int
    write_max: int
    count: int

    @dataclass
    class Insert:
        port: int
        read_min: int
        read_max: int
        write_min: int
        write_max: int
        count: int = 1

    @dataclass
    class Increment:
        port: int
        read_min: int
        read_max: int
        write_min: int
        write_max: int
        count: int = 1


@dataclass
class TcpEventRow:
    id: int
    connection_id: int
    timestamp: int
    event_type: str
    data: bytes | None
    data_text: str | None
    data_size: int
    end_stream: int
    truncated: int

    @dataclass
    class Insert:
        connection_id: int
        timestamp: int
        event_type: str
        data: bytes | None = None
        data_text: str | None = None
        data_size: int = 0
        end_stream: bool = False
        truncated: bool = False


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
            INSERT INTO alert (created, port, http_request_id, http_response_id, tcp_connection_id, description)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row.created,
                row.port,
                row.http_request_id,
                row.http_response_id,
                row.tcp_connection_id,
                row.description,
            ),
        )


class FlagTable(BaseTable):
    def insert_many(self, tx: sqlite3.Cursor, flags: list[FlagRow.Insert]) -> None:
        tx.executemany(
            """
            INSERT INTO flag (http_request_id, http_response_id, tcp_connection_id, tcp_event_id, location, offset, value)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f.http_request_id,
                    f.http_response_id,
                    f.tcp_connection_id,
                    f.tcp_event_id,
                    f.location,
                    f.offset,
                    f.value,
                )
                for f in flags
            ],
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


@dataclass
class SessionLinkRow:
    id: int
    session_id: int
    http_request_id: int

    @dataclass
    class Insert:
        session_key: str
        port: int
        http_request_id: int


class SessionTable(BaseTable):
    def upsert(self, tx: sqlite3.Cursor, port: int, key: str) -> int:
        """Upsert session and increment count. Returns session ID."""
        tx.execute(
            """
            INSERT INTO session (port, key, count)
            VALUES (?, ?, 1)
            ON CONFLICT(port, key) DO UPDATE SET count = count + 1
            RETURNING id
            """,
            (port, key),
        )
        return tx.fetchone()[0]

    def get_by_key(self, port: int, key: str) -> SessionRow | None:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM session WHERE port = ? AND key = ?",
                (port, key),
            )
            row = cursor.fetchone()
            if row:
                return SessionRow(**dict(row))
            return None


class SessionLinkTable(BaseTable):
    def insert(self, tx: sqlite3.Cursor, row: SessionLinkRow.Insert) -> None:
        session_table = SessionTable(self.db_file)
        session_id = session_table.upsert(tx, row.port, row.session_key)

        tx.execute(
            """
            INSERT OR IGNORE INTO session_link (session_id, http_request_id)
            VALUES (?, ?)
            """,
            (session_id, row.http_request_id),
        )

    def get_requests_by_session(self, port: int, session_key: str) -> list[int]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT sl.http_request_id
                FROM session_link sl
                JOIN session s ON s.id = sl.session_id
                WHERE s.port = ? AND s.key = ?
                ORDER BY sl.http_request_id
                """,
                (port, session_key),
            )
            return [row[0] for row in cursor.fetchall()]

    def get_session_for_request(self, request_id: int) -> tuple[int, str] | None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT s.port, s.key
                FROM session s
                JOIN session_link sl ON sl.session_id = s.id
                WHERE sl.http_request_id = ?
                """,
                (request_id,),
            )
            result = cursor.fetchone()
            if result:
                return result
            return None

    def get_related_requests(self, request_id: int) -> list[int]:
        session_info = self.get_session_for_request(request_id)
        if not session_info:
            return []
        port, session_key = session_info
        requests = self.get_requests_by_session(port, session_key)
        return [r for r in requests if r != request_id]


class TcpConnectionTable(BaseTable):
    def insert(self, tx: sqlite3.Cursor, **kwargs) -> int:
        row = (
            TcpConnectionRow.Insert(**kwargs)
            if not isinstance(kwargs.get("port"), TcpConnectionRow.Insert)
            else kwargs["port"]
        )
        if isinstance(kwargs.get("port"), TcpConnectionRow.Insert):
            row = kwargs["port"]
        else:
            row = TcpConnectionRow.Insert(**kwargs)

        tx.execute(
            """
            INSERT INTO tcp_connection (
                port, connection_id, start_time, duration_ms,
                bytes_in, bytes_out, is_blocked, tap_id, batch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.port,
                row.connection_id,
                row.start_time,
                row.duration_ms,
                row.bytes_in,
                row.bytes_out,
                int(row.is_blocked),
                row.tap_id,
                row.batch_id,
            ),
        )
        return tx.lastrowid


class TcpEventTable(BaseTable):
    def insert(self, tx: sqlite3.Cursor, **kwargs) -> int:
        row = TcpEventRow.Insert(**kwargs)

        tx.execute(
            """
            INSERT INTO tcp_event (
                connection_id, timestamp, event_type, data, data_text,
                data_size, end_stream, truncated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.connection_id,
                row.timestamp,
                row.event_type,
                row.data,
                row.data_text,
                row.data_size,
                int(row.end_stream),
                int(row.truncated),
            ),
        )
        return tx.lastrowid


class TcpConnectionStatsTable(BaseTable):
    def increment(self, tx: sqlite3.Cursor, row: TcpConnectionStatsRow.Increment) -> RowStatus:
        # Try to update existing record
        tx.execute(
            """
            UPDATE tcp_connection_stats
            SET count = count + ?
            WHERE port = ? AND read_min = ? AND read_max = ? AND write_min = ? AND write_max = ?
        """,
            (row.count, row.port, row.read_min, row.read_max, row.write_min, row.write_max),
        )

        if tx.rowcount == 0:
            # Insert new record if not exists
            tx.execute(
                """
                INSERT INTO tcp_connection_stats (port, read_min, read_max, write_min, write_max, count)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (row.port, row.read_min, row.read_max, row.write_min, row.write_max, row.count),
            )
            return RowStatus.NEW

        return RowStatus.UPDATED

    def get_by_port(self, port: int) -> list[TcpConnectionStatsRow]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM tcp_connection_stats
                WHERE port = ?
                ORDER BY read_min, write_min
            """,
                (port,),
            )
            rows = cursor.fetchall()
            return [TcpConnectionStatsRow(**dict(row)) for row in rows]


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
        self.http_path_time_stats = HttpPathTimeStatsTable()
        self.http_query_param_time_stats = HttpQueryParamTimeStatsTable()
        self.http_header_time_stats = HttpHeaderTimeStatsTable()
        self.http_request_time_stats = HttpRequestTimeStatsTable()
        self.flag_time_stats = FlagTimeStatsTable()
        self.sessions = SessionTable(db_file)
        self.session_links = SessionLinkTable(db_file)
        self.tcp_connections = TcpConnectionTable(db_file)
        self.tcp_events = TcpEventTable(db_file)
        self.tcp_connection_stats = TcpConnectionStatsTable(db_file)
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

    def execute_sql(
        self, query: str, default_limit: int = 1000, timeout: float = 10.0
    ) -> SqlExecutionResult:
        """Execute a SQL query and return results as list of dicts with column names.

        Args:
            query: The SQL query to execute (must be a SELECT query)
            default_limit: Default limit to apply if query doesn't have one
            timeout: Query execution timeout in seconds (default: 10.0)

        Returns:
            SqlExecutionResult with rows, columns, and query execution time

        Raises:
            ValueError: If query is not a SELECT statement
            sqlite3.Error: If query execution fails
            TimeoutError: If query execution exceeds timeout
        """
        query = query.strip()
        while query.endswith(";"):
            query = query[:-1].rstrip()

        query_upper = query.upper()

        if not query_upper.startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed")

        if default_limit and "LIMIT" not in query_upper:
            query = f"{query} LIMIT {default_limit}"

        results = []
        columns = []
        exception = None
        conn = None
        query_time = 0

        def execute_query():
            nonlocal results, columns, exception, conn, query_time
            try:
                conn = sqlite3.connect(self.db_file)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                start_time = time.perf_counter()
                cursor.execute(query)
                rows = cursor.fetchall()
                query_time = (time.perf_counter() - start_time) * 1000

                if rows:
                    columns = list(rows[0].keys())
                    results = [dict(row) for row in rows]
                else:
                    columns = []
                    results = []
            except Exception as e:
                exception = e
            finally:
                if conn:
                    conn.close()

        thread = threading.Thread(target=execute_query)
        thread.daemon = True
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # Query is still running after timeout
            # Interrupt the connection to stop the query
            if conn:
                try:
                    conn.interrupt()
                except Exception:
                    pass
            raise TimeoutError(f"Query execution exceeded {timeout} seconds timeout")

        if exception:
            raise exception

        return SqlExecutionResult(rows=results, columns=columns, query_time_ms=query_time)
