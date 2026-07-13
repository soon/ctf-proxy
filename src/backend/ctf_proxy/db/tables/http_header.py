
from dataclasses import dataclass
from typing import ClassVar

from psycopg import Cursor

from ctf_proxy.db.connection import Row, nul_safe
from ctf_proxy.db.refs import Ref


@dataclass
class HttpHeaderRow:
    id: int
    name: str
    value: str
    request_id: int | None = None
    response_id: int | None = None

    @dataclass
    class Insert:
        TABLE: ClassVar[str] = "http_header"
        name: str
        value: str
        request_id: "int | None | Ref" = None
        response_id: "int | None | Ref" = None


class HttpHeaderTable:
    def insert_many(self, tx: Cursor, headers: list[HttpHeaderRow.Insert]) -> None:
        tx.executemany(
            """
            INSERT INTO http_header (request_id, response_id, name, value)
            VALUES (%s, %s, %s, %s)
            """,
            [
                (h.request_id, h.response_id, nul_safe(h.name), nul_safe(h.value))
                for h in headers
            ],
        )

    def get_by_request_ids(
        self, tx: Cursor, request_ids: list[int]
    ) -> list[Row]:
        placeholders = ",".join(["%s"] * len(request_ids))
        return tx.execute(
            f"SELECT request_id, name, value FROM http_header WHERE request_id IN ({placeholders})",
            request_ids,
        ).fetchall()

    def get_by_response_ids(
        self, tx: Cursor, response_ids: list[int]
    ) -> list[Row]:
        placeholders = ",".join(["%s"] * len(response_ids))
        return tx.execute(
            f"SELECT response_id, name, value FROM http_header WHERE response_id IN ({placeholders})",
            response_ids,
        ).fetchall()
