from dataclasses import dataclass


@dataclass(frozen=True)
class TcpEvent:
    event_type: str
    data_text: str | None
    data_size: int
    end_stream: bool
    truncated: bool


@dataclass(frozen=True)
class ConnectionContext:
    id: int
    port: int
    connection_id: int
    start_time: int
    duration_ms: int | None
    bytes_in: int
    bytes_out: int
    is_blocked: bool
    batch_id: str | None
    events: tuple[TcpEvent, ...]

    @property
    def read_text(self) -> str:
        return "\n".join(e.data_text or "" for e in self.events if e.event_type == "read")

    @property
    def write_text(self) -> str:
        return "\n".join(e.data_text or "" for e in self.events if e.event_type == "write")

    @property
    def text(self) -> str:
        return "\n".join(e.data_text or "" for e in self.events)


@dataclass(frozen=True)
class RequestContext:
    id: int
    port: int
    start_time: int
    method: str
    path: str
    user_agent: str | None
    body: str | None
    is_blocked: bool
    is_websocket: bool
    status: int | None
    response_body: str | None
    request_headers: dict[str, str]
    response_headers: dict[str, str]
    batch_id: str | None

    def request_header(self, name: str) -> str | None:
        return self.lookup_header(self.request_headers, name)

    def response_header(self, name: str) -> str | None:
        return self.lookup_header(self.response_headers, name)

    @staticmethod
    def lookup_header(headers: dict[str, str], name: str) -> str | None:
        target = name.lower()
        for key, value in headers.items():
            if key.lower() == target:
                return value
        return None
