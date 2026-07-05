import sqlite3

from ctf_proxy.analyzer.context import ConnectionContext, RequestContext, TcpEvent


class SourceReader:
    def __init__(self, db_file: str):
        self.db_file = db_file

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn

    def has_table(self, conn: sqlite3.Connection, name: str) -> bool:
        return (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
            ).fetchone()
            is not None
        )

    def max_source_id(self) -> int:
        with self.connect() as conn:
            if not (self.has_table(conn, "http_request") or self.has_table(conn, "tcp_connection")):
                return 0
            row = conn.execute(
                "SELECT MAX(m) FROM ("
                "  SELECT MAX(id) AS m FROM http_request"
                "  UNION ALL SELECT MAX(id) AS m FROM tcp_connection"
                ")"
            ).fetchone()
            return row[0] or 0

    def read_http_batch(self, last_id: int, limit: int) -> list[RequestContext]:
        with self.connect() as conn:
            if not self.has_table(conn, "http_request"):
                return []
            requests = conn.execute(
                "SELECT * FROM http_request WHERE id > ? ORDER BY id LIMIT ?",
                (last_id, limit),
            ).fetchall()
            return self.hydrate_http(conn, requests)

    def read_http_backfill(
        self, last_id: int, target_id: int, ports: list[int] | None, limit: int
    ) -> list[RequestContext]:
        with self.connect() as conn:
            if not self.has_table(conn, "http_request"):
                return []
            params: list[int] = [last_id, target_id]
            port_clause = ""
            if ports:
                placeholders = ",".join("?" * len(ports))
                port_clause = f" AND port IN ({placeholders})"
                params.extend(ports)
            params.append(limit)
            requests = conn.execute(
                f"SELECT * FROM http_request WHERE id > ? AND id <= ?{port_clause} "
                f"ORDER BY id LIMIT ?",
                params,
            ).fetchall()
            return self.hydrate_http(conn, requests)

    def read_http_by_ids(self, ids: list[int]) -> list[RequestContext]:
        if not ids:
            return []
        with self.connect() as conn:
            if not self.has_table(conn, "http_request"):
                return []
            placeholders = ",".join("?" * len(ids))
            requests = conn.execute(
                f"SELECT * FROM http_request WHERE id IN ({placeholders}) ORDER BY id",
                ids,
            ).fetchall()
            return self.hydrate_http(conn, requests)

    def hydrate_http(self, conn, requests) -> list[RequestContext]:
        if not requests:
            return []

        request_ids = [r["id"] for r in requests]
        request_placeholders = ",".join("?" * len(request_ids))

        responses = {
            row["request_id"]: row
            for row in conn.execute(
                f"SELECT * FROM http_response WHERE request_id IN ({request_placeholders})",
                request_ids,
            ).fetchall()
        }

        request_headers: dict[int, dict[str, str]] = {}
        for row in conn.execute(
            f"SELECT request_id, name, value FROM http_header WHERE request_id IN ({request_placeholders})",
            request_ids,
        ).fetchall():
            request_headers.setdefault(row["request_id"], {})[row["name"]] = row["value"]

        response_ids = [row["id"] for row in responses.values()]
        response_headers: dict[int, dict[str, str]] = {}
        if response_ids:
            response_placeholders = ",".join("?" * len(response_ids))
            for row in conn.execute(
                f"SELECT response_id, name, value FROM http_header WHERE response_id IN ({response_placeholders})",
                response_ids,
            ).fetchall():
                response_headers.setdefault(row["response_id"], {})[row["name"]] = row["value"]

        contexts: list[RequestContext] = []
        for r in requests:
            response = responses.get(r["id"])
            response_id = response["id"] if response else None
            contexts.append(
                RequestContext(
                    id=r["id"],
                    port=r["port"],
                    start_time=r["start_time"],
                    method=r["method"],
                    path=r["path"],
                    user_agent=r["user_agent"],
                    body=r["body"],
                    is_blocked=bool(r["is_blocked"]),
                    is_websocket=bool(r["is_websocket"]),
                    status=response["status"] if response else None,
                    response_body=response["body"] if response else None,
                    request_headers=request_headers.get(r["id"], {}),
                    response_headers=response_headers.get(response_id, {}) if response_id else {},
                    batch_id=r["batch_id"],
                )
            )
        return contexts

    def read_tcp_batch(self, last_id: int, limit: int) -> list[ConnectionContext]:
        with self.connect() as conn:
            if not self.has_table(conn, "tcp_connection"):
                return []
            connections = conn.execute(
                "SELECT * FROM tcp_connection WHERE id > ? ORDER BY id LIMIT ?",
                (last_id, limit),
            ).fetchall()
            return self.hydrate_tcp(conn, connections)

    def read_tcp_backfill(
        self, last_id: int, target_id: int, ports: list[int] | None, limit: int
    ) -> list[ConnectionContext]:
        with self.connect() as conn:
            if not self.has_table(conn, "tcp_connection"):
                return []
            params: list[int] = [last_id, target_id]
            port_clause = ""
            if ports:
                placeholders = ",".join("?" * len(ports))
                port_clause = f" AND port IN ({placeholders})"
                params.extend(ports)
            params.append(limit)
            connections = conn.execute(
                f"SELECT * FROM tcp_connection WHERE id > ? AND id <= ?{port_clause} "
                f"ORDER BY id LIMIT ?",
                params,
            ).fetchall()
            return self.hydrate_tcp(conn, connections)

    def read_tcp_by_ids(self, ids: list[int]) -> list[ConnectionContext]:
        if not ids:
            return []
        with self.connect() as conn:
            if not self.has_table(conn, "tcp_connection"):
                return []
            placeholders = ",".join("?" * len(ids))
            connections = conn.execute(
                f"SELECT * FROM tcp_connection WHERE id IN ({placeholders}) ORDER BY id",
                ids,
            ).fetchall()
            return self.hydrate_tcp(conn, connections)

    def hydrate_tcp(self, conn, connections) -> list[ConnectionContext]:
        if not connections:
            return []

        connection_ids = [c["id"] for c in connections]
        placeholders = ",".join("?" * len(connection_ids))

        events: dict[int, list[TcpEvent]] = {}
        for row in conn.execute(
            f"SELECT connection_id, event_type, data_text, data_size, end_stream, truncated "
            f"FROM tcp_event WHERE connection_id IN ({placeholders}) ORDER BY id",
            connection_ids,
        ).fetchall():
            events.setdefault(row["connection_id"], []).append(
                TcpEvent(
                    event_type=row["event_type"],
                    data_text=row["data_text"],
                    data_size=row["data_size"],
                    end_stream=bool(row["end_stream"]),
                    truncated=bool(row["truncated"]),
                )
            )

        contexts: list[ConnectionContext] = []
        for c in connections:
            contexts.append(
                ConnectionContext(
                    id=c["id"],
                    port=c["port"],
                    connection_id=c["connection_id"],
                    start_time=c["start_time"],
                    duration_ms=c["duration_ms"],
                    bytes_in=c["bytes_in"],
                    bytes_out=c["bytes_out"],
                    is_blocked=bool(c["is_blocked"]),
                    batch_id=c["batch_id"],
                    events=tuple(events.get(c["id"], ())),
                )
            )
        return contexts
