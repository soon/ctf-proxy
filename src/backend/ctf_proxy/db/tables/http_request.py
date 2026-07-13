
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from psycopg import Cursor

from ctf_proxy.db.connection import Row, nul_safe


@dataclass
class HttpRequestRow:
    id: int
    port: int
    start_time: datetime
    path: str
    method: str
    user_agent: str | None
    body: str | None
    is_blocked: bool
    is_websocket: bool
    tap_id: str | None
    batch_id: str | None
    request_headers: str | None

    @dataclass
    class Insert:
        TABLE: ClassVar[str] = "http_request"
        RETURNING: ClassVar[bool] = True
        port: int
        start_time: int
        path: str
        method: str
        is_blocked: int
        user_agent: str | None = None
        body: str | None = None
        is_websocket: int = 0
        tap_id: str | None = None
        batch_id: str | None = None
        request_headers: str | None = None


class HttpRequestTable:
    def insert(
        self,
        tx: Cursor,
        port: int,
        start_time: int,
        path: str,
        method: str,
        user_agent: str | None = None,
        body: str | None = None,
        is_blocked: bool | None = False,
        is_websocket: bool = False,
        tap_id: str | None = None,
        batch_id: str | None = None,
        request_headers: str | None = None,
    ) -> int:
        tx.execute(
            """
            INSERT INTO http_request (port, start_time, path, method, user_agent, body, is_blocked, is_websocket, tap_id, batch_id, request_headers)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (
                port,
                start_time,
                nul_safe(path),
                method,
                nul_safe(user_agent),
                nul_safe(body),
                int(bool(is_blocked)),
                int(bool(is_websocket)),
                tap_id,
                batch_id,
                nul_safe(request_headers),
            ),
        )
        return tx.fetchone()[0]

    def read_after(self, tx: Cursor, last_id: int, limit: int) -> list[Row]:
        return tx.execute(
            "SELECT * FROM http_request WHERE id > %s ORDER BY id LIMIT %s",
            (last_id, limit),
        ).fetchall()

    def read_range(
        self,
        tx: Cursor,
        last_id: int,
        target_id: int,
        ports: list[int] | None,
        limit: int,
    ) -> list[Row]:
        params: list[int] = [last_id, target_id]
        port_clause = ""
        if ports:
            placeholders = ",".join(["%s"] * len(ports))
            port_clause = f" AND port IN ({placeholders})"
            params.extend(ports)
        params.append(limit)
        return tx.execute(
            f"SELECT * FROM http_request WHERE id > %s AND id <= %s{port_clause} ORDER BY id LIMIT %s",
            params,
        ).fetchall()

    def read_by_ids(self, tx: Cursor, ids: list[int]) -> list[Row]:
        placeholders = ",".join(["%s"] * len(ids))
        return tx.execute(
            f"SELECT * FROM http_request WHERE id IN ({placeholders}) ORDER BY id",
            ids,
        ).fetchall()
