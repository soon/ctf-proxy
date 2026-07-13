
from dataclasses import dataclass
from typing import ClassVar

from psycopg import Cursor

from ctf_proxy.db.connection import Row, nul_safe
from ctf_proxy.db.refs import Ref


@dataclass
class HttpResponseRow:
    id: int
    request_id: int
    status: int
    body: str | None
    response_headers: str | None

    @dataclass
    class Insert:
        TABLE: ClassVar[str] = "http_response"
        RETURNING: ClassVar[bool] = True
        request_id: "int | Ref"
        status: int
        body: str | None = None
        response_headers: str | None = None


class HttpResponseTable:
    def insert(
        self,
        tx: Cursor,
        request_id: int,
        status: int,
        body: str | None = None,
        response_headers: str | None = None,
    ) -> int:
        tx.execute(
            """
            INSERT INTO http_response (request_id, status, body, response_headers)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (request_id, status, nul_safe(body), nul_safe(response_headers)),
        )
        return tx.fetchone()[0]

    def get_by_request_ids(
        self, tx: Cursor, request_ids: list[int]
    ) -> list[Row]:
        placeholders = ",".join(["%s"] * len(request_ids))
        return tx.execute(
            f"SELECT * FROM http_response WHERE request_id IN ({placeholders})",
            request_ids,
        ).fetchall()
