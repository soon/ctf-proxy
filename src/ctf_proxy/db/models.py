#!/usr/bin/env python3

from contextlib import closing
import logging
import os
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class HttpRequestRow:
    id: int
    port: int
    start_time: datetime
    path: str
    method: str
    user_agent: Optional[str]
    body: Optional[str]
    tap_id: Optional[str]
    batch_id: Optional[str]


@dataclass
class HttpResponseRow:
    id: int
    request_id: int
    status: int
    body: Optional[str]


@dataclass
class HttpHeaderRow:
    id: int
    name: str
    value: str
    request_id: Optional[int] = None
    response_id: Optional[int] = None

    @dataclass
    class Insert:
        name: str
        value: str
        request_id: Optional[int] = None
        response_id: Optional[int] = None


@dataclass
class AlertRow:
    id: str
    created: datetime
    port: int
    description: str
    http_request_id: Optional[int] = None
    http_response_id: Optional[int] = None


@dataclass
class BatchRow:
    id: str
    created: int
    file_count: int
    archive_file: Optional[str]
    processed: bool


class BaseTable(ABC):
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
        user_agent: Optional[str] = None,
        body: Optional[str] = None,
        tap_id: Optional[str] = None,
        batch_id: Optional[str] = None,
    ) -> int:
        tx.execute(
            """
            INSERT INTO http_request (port, start_time, path, method, user_agent, body, tap_id, batch_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (port, start_time, path, method, user_agent, body, tap_id, batch_id),
        )
        return tx.lastrowid

    def get_by_id(self, request_id: int) -> Optional[HttpRequestRow]:
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
    def insert(self, tx: sqlite3.Cursor, request_id: int, status: int, body: Optional[str] = None) -> int:
        tx.execute(
            """
            INSERT INTO http_response (request_id, status, body)
            VALUES (?, ?, ?)
            """,
            (request_id, status, body),
        )
        return tx.lastrowid

    def get_by_request_id(self, request_id: int) -> Optional[HttpResponseRow]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM http_response WHERE request_id = ?", (request_id,))
            row = cursor.fetchone()
            if row:
                return HttpResponseRow(**dict(row))
            return None


class HttpHeaderTable(BaseTable):
    def insert(
        self,
        name: str,
        value: str,
        request_id: Optional[int] = None,
        response_id: Optional[int] = None,
    ) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO http_header (request_id, response_id, name, value)
                VALUES (?, ?, ?, ?)
                """,
                (request_id, response_id, name, value),
            )
            return cursor.lastrowid

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
        alert_id: str,
        port: int,
        description: str,
        http_request_id: Optional[int] = None,
        http_response_id: Optional[int] = None,
        created: Optional[datetime] = None,
    ) -> None:
        if created is None:
            created = datetime.now()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO alert (id, created, port, http_request_id, http_response_id, description)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (alert_id, created, port, http_request_id, http_response_id, description),
            )

    def get_by_port(self, port: int) -> list[AlertRow]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM alert WHERE port = ? ORDER BY created DESC", (port,))
            rows = cursor.fetchall()
            return [AlertRow(**dict(row)) for row in rows]

    def get_all(self, limit: int = 100) -> list[AlertRow]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM alert ORDER BY created DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [AlertRow(**dict(row)) for row in rows]


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
        
        with open(schema_file, 'r') as f:
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
