from dataclasses import dataclass

from psycopg import Cursor


@dataclass
class BackfillJob:
    id: int
    target_id: int
    ports: list[int] | None
    http_cursor: int
    tcp_cursor: int
    status: str


def encode_ports(ports: list[int] | None) -> str | None:
    if not ports:
        return None
    return ",".join(str(p) for p in ports)


def decode_ports(value: str | None) -> list[int] | None:
    if not value:
        return None
    return [int(p) for p in value.split(",") if p]


class BackfillJobTable:
    def create(
        self, tx: Cursor, target_id: int, ports: list[int] | None, created: int
    ) -> int:
        tx.execute(
            """
            INSERT INTO backfill_job (target_id, ports, status, created, updated)
            VALUES (%s, %s, 'pending', %s, %s) RETURNING id
            """,
            (target_id, encode_ports(ports), created, created),
        )
        return tx.fetchone()[0]

    def active(self, tx: Cursor) -> BackfillJob | None:
        tx.execute(
            """
            SELECT id, target_id, ports, http_cursor, tcp_cursor, status
            FROM backfill_job WHERE status IN ('pending', 'running')
            ORDER BY id LIMIT 1
            """
        )
        row = tx.fetchone()
        return self.row_to_job(row) if row else None

    def latest(self, tx: Cursor) -> BackfillJob | None:
        tx.execute(
            """
            SELECT id, target_id, ports, http_cursor, tcp_cursor, status
            FROM backfill_job ORDER BY id DESC LIMIT 1
            """
        )
        row = tx.fetchone()
        return self.row_to_job(row) if row else None

    def row_to_job(self, row) -> BackfillJob:
        return BackfillJob(
            id=row[0],
            target_id=row[1],
            ports=decode_ports(row[2]),
            http_cursor=row[3],
            tcp_cursor=row[4],
            status=row[5],
        )

    def update(self, tx: Cursor, job_id: int, updated: int, **fields) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = %s" for key in fields)
        values = list(fields.values())
        tx.execute(
            f"UPDATE backfill_job SET {assignments}, updated = %s WHERE id = %s",
            (*values, updated, job_id),
        )
