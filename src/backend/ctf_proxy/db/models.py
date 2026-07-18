#!/usr/bin/env python3

import logging
import os
import time
from dataclasses import dataclass

import psycopg

from ctf_proxy.db import connection
from ctf_proxy.db.base import RowStatus
from ctf_proxy.db.stats import (
    FlagTimeStatsTable,
    HttpHeaderTimeStatsTable,
    HttpPathTimeStatsTable,
    HttpQueryParamTimeStatsTable,
    HttpRequestTimeStatsTable,
)
from ctf_proxy.db.tables.flag import FlagRow, FlagTable
from ctf_proxy.db.tables.http_header import HttpHeaderRow, HttpHeaderTable
from ctf_proxy.db.tables.http_path_stats import HttpPathStatsRow, HttpPathStatsTable
from ctf_proxy.db.tables.http_request import HttpRequestRow, HttpRequestTable
from ctf_proxy.db.tables.http_response import HttpResponseRow, HttpResponseTable
from ctf_proxy.db.tables.http_response_code_stats import (
    HttpResponseCodeStatsRow,
    HttpResponseCodeStatsTable,
)
from ctf_proxy.db.tables.service_stats import ServiceStatsRow, ServiceStatsTable
from ctf_proxy.db.tables.session import SessionRow, SessionTable
from ctf_proxy.db.tables.session_link import SessionLinkRow, SessionLinkTable
from ctf_proxy.db.tables.tcp_connection import TcpConnectionRow, TcpConnectionTable
from ctf_proxy.db.tables.tcp_connection_stats import (
    TcpConnectionStatsRow,
    TcpConnectionStatsTable,
)
from ctf_proxy.db.tables.tcp_connection_time_stats import TcpConnectionTimeStatsTable
from ctf_proxy.db.tables.tcp_event import TcpEventRow, TcpEventTable
from ctf_proxy.db.tables.tcp_stats import TcpStatsTable
from ctf_proxy.db.tables.websocket_connection import (
    WebSocketConnectionRow,
    WebSocketConnectionTable,
)
from ctf_proxy.db.tables.websocket_frame import WebSocketFrameRow, WebSocketFrameTable

logger = logging.getLogger(__name__)


__all__ = [
    "RowStatus",
    "SqlExecutionResult",
    "FlagRow",
    "FlagTable",
    "HttpHeaderRow",
    "HttpHeaderTable",
    "HttpPathStatsRow",
    "HttpPathStatsTable",
    "HttpRequestRow",
    "HttpRequestTable",
    "HttpResponseRow",
    "HttpResponseTable",
    "HttpResponseCodeStatsRow",
    "HttpResponseCodeStatsTable",
    "ServiceStatsRow",
    "ServiceStatsTable",
    "SessionRow",
    "SessionTable",
    "SessionLinkRow",
    "SessionLinkTable",
    "TcpConnectionRow",
    "TcpConnectionTable",
    "TcpConnectionStatsRow",
    "TcpConnectionStatsTable",
    "TcpConnectionTimeStatsTable",
    "TcpStatsTable",
    "TcpEventRow",
    "TcpEventTable",
    "WebSocketConnectionRow",
    "WebSocketConnectionTable",
    "WebSocketFrameRow",
    "WebSocketFrameTable",
    "FlagTimeStatsTable",
    "HttpHeaderTimeStatsTable",
    "HttpPathTimeStatsTable",
    "HttpQueryParamTimeStatsTable",
    "HttpRequestTimeStatsTable",
    "ProxyStatsDB",
    "make_db",
]


@dataclass
class SqlExecutionResult:
    rows: list[dict]
    columns: list[str]
    query_time_ms: float


class ProxyStatsDB:
    def __init__(self):
        self.http_requests = HttpRequestTable()
        self.http_responses = HttpResponseTable()
        self.http_headers = HttpHeaderTable()
        self.flags = FlagTable()
        self.service_stats = ServiceStatsTable()
        self.http_response_code_stats = HttpResponseCodeStatsTable()
        self.http_path_stats = HttpPathStatsTable()
        self.http_path_time_stats = HttpPathTimeStatsTable()
        self.http_query_param_time_stats = HttpQueryParamTimeStatsTable()
        self.http_header_time_stats = HttpHeaderTimeStatsTable()
        self.http_request_time_stats = HttpRequestTimeStatsTable()
        self.flag_time_stats = FlagTimeStatsTable()
        self.sessions = SessionTable()
        self.session_links = SessionLinkTable()
        self.tcp_connections = TcpConnectionTable()
        self.tcp_events = TcpEventTable()
        self.tcp_connection_stats = TcpConnectionStatsTable()
        self.tcp_connection_time_stats = TcpConnectionTimeStatsTable()
        self.tcp_stats = TcpStatsTable()
        self.websocket_connections = WebSocketConnectionTable()
        self.websocket_frames = WebSocketFrameTable()

    def connect(self):
        return connection.connect()

    def table_exists(self, tx, name: str) -> bool:
        qualified = name if "." in name else f"logs.{name}"
        return tx.execute("SELECT to_regclass(%s) IS NOT NULL", (qualified,)).fetchone()[0]

    def max_source_id(self) -> int:
        with self.connect() as conn:
            if not (
                self.table_exists(conn, "http_request") or self.table_exists(conn, "tcp_connection")
            ):
                return 0
            row = conn.execute(
                "SELECT MAX(m) FROM ("
                "  SELECT MAX(id) AS m FROM http_request"
                "  UNION ALL SELECT MAX(id) AS m FROM tcp_connection"
                ") AS t"
            ).fetchone()
            return row[0] or 0

    def init_schema(self, schema_file: str = None) -> None:
        if schema_file is None:
            schema_file = os.path.join(os.path.dirname(__file__), "schema.sql")

        if not os.path.exists(schema_file):
            logger.error(f"Schema file not found: {schema_file}")
            return

        with open(schema_file) as f:
            schema_sql = f.read()

        with self.connect() as conn:
            conn.execute(schema_sql)
            conn.commit()

        logger.info(f"Database schema initialized from {schema_file}")

    def init_db(self) -> None:
        self.init_schema()
        logger.info(f"Database initialized: {connection.describe()}")

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
            psycopg.Error: If query execution fails
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

        timeout_ms = int(timeout * 1000)
        with connection.connect(statement_timeout_ms=timeout_ms) as conn:
            cursor = conn.cursor()
            start_time = time.perf_counter()
            try:
                cursor.execute(query)
                rows = cursor.fetchall()
            except psycopg.errors.QueryCanceled as e:
                raise TimeoutError(f"Query execution exceeded {timeout} seconds timeout") from e
            query_time = (time.perf_counter() - start_time) * 1000

            if rows:
                columns = list(rows[0].keys())
                results = [dict(zip(columns, row, strict=False)) for row in rows]
            else:
                columns = []
                results = []

        return SqlExecutionResult(rows=results, columns=columns, query_time_ms=query_time)


def make_db() -> ProxyStatsDB:
    db = ProxyStatsDB()
    db.init_db()
    return db
