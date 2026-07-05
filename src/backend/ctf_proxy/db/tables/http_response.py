
from dataclasses import dataclass

from psycopg import Cursor

from ctf_proxy.db.connection import Row, nul_safe


@dataclass
class HttpResponseRow:
    id: int
    request_id: int
    status: int
    body: str | None


class HttpResponseTable:
    def insert(
        self, tx: Cursor, request_id: int, status: int, body: str | None = None
    ) -> int:
        tx.execute(
            """
            INSERT INTO http_response (request_id, status, body)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (request_id, status, nul_safe(body)),
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
