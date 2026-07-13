import psycopg

from ctf_proxy.analytics.context import ConnectionContext, RequestContext, TcpEvent
from ctf_proxy.db.models import ProxyStatsDB
from ctf_proxy.db.utils import parse_headers


class SourceReader:
    def __init__(self):
        self.db = ProxyStatsDB()

    def connect(self) -> psycopg.Connection:
        return self.db.connect()

    def max_source_id(self) -> int:
        return self.db.max_source_id()

    def read_http_batch(self, last_id: int, limit: int) -> list[RequestContext]:
        with self.connect() as conn:
            if not self.db.table_exists(conn, "http_request"):
                return []
            requests = self.db.http_requests.read_after(conn, last_id, limit)
            return self.hydrate_http(conn, requests)

    def read_http_backfill(
        self, last_id: int, target_id: int, ports: list[int] | None, limit: int
    ) -> list[RequestContext]:
        with self.connect() as conn:
            if not self.db.table_exists(conn, "http_request"):
                return []
            requests = self.db.http_requests.read_range(conn, last_id, target_id, ports, limit)
            return self.hydrate_http(conn, requests)

    def read_http_by_ids(self, ids: list[int]) -> list[RequestContext]:
        if not ids:
            return []
        with self.connect() as conn:
            if not self.db.table_exists(conn, "http_request"):
                return []
            requests = self.db.http_requests.read_by_ids(conn, ids)
            return self.hydrate_http(conn, requests)

    def hydrate_http(self, conn, requests) -> list[RequestContext]:
        if not requests:
            return []

        request_ids = [r["id"] for r in requests]

        responses = {
            row["request_id"]: row
            for row in self.db.http_responses.get_by_request_ids(conn, request_ids)
        }

        request_headers = {r["id"]: dict(parse_headers(r["request_headers"])) for r in requests}
        response_headers = {
            resp["id"]: dict(parse_headers(resp["response_headers"]))
            for resp in responses.values()
        }

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
            if not self.db.table_exists(conn, "tcp_connection"):
                return []
            connections = self.db.tcp_connections.read_after(conn, last_id, limit)
            return self.hydrate_tcp(conn, connections)

    def read_tcp_backfill(
        self, last_id: int, target_id: int, ports: list[int] | None, limit: int
    ) -> list[ConnectionContext]:
        with self.connect() as conn:
            if not self.db.table_exists(conn, "tcp_connection"):
                return []
            connections = self.db.tcp_connections.read_range(conn, last_id, target_id, ports, limit)
            return self.hydrate_tcp(conn, connections)

    def read_tcp_by_ids(self, ids: list[int]) -> list[ConnectionContext]:
        if not ids:
            return []
        with self.connect() as conn:
            if not self.db.table_exists(conn, "tcp_connection"):
                return []
            connections = self.db.tcp_connections.read_by_ids(conn, ids)
            return self.hydrate_tcp(conn, connections)

    def hydrate_tcp(self, conn, connections) -> list[ConnectionContext]:
        if not connections:
            return []

        connection_ids = [c["id"] for c in connections]

        events: dict[int, list[TcpEvent]] = {}
        for row in self.db.tcp_events.get_by_connection_ids(conn, connection_ids):
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
