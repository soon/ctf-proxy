from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ServiceInfo(BaseModel):
    name: str
    port: int
    type: str


class TCPStats(BaseModel):
    total_connections: int
    total_bytes_in: int
    total_bytes_out: int
    avg_duration_ms: int
    total_flags_found: int


class ServiceStats(BaseModel):
    total_requests: int
    blocked_requests: int
    total_responses: int
    blocked_responses: int
    error_responses: int
    success_responses: int
    redirect_responses: int
    status_counts: dict[int, int]
    unique_paths: int
    alerts_count: int
    recent_alerts: list[tuple[str, Any]]
    flags_written: int
    flags_retrieved: int
    flags_blocked: int
    total_flags: int
    unique_headers: int
    unique_header_values: int
    tcp_stats: TCPStats | None = None


class ServiceListItem(BaseModel):
    name: str
    port: int
    type: str
    stats: ServiceStats


class ServiceListResponse(BaseModel):
    services: list[ServiceListItem]
    timestamp: datetime


class RequestListItem(BaseModel):
    id: int
    timestamp: datetime
    method: str
    path: str
    status: int | None
    is_blocked: bool
    user_agent: str
    request_flags: int
    response_flags: int
    incoming_links: int
    outgoing_links: int


class RequestListResponse(BaseModel):
    requests: list[RequestListItem]
    total: int
    service_name: str
    service_port: int
    page: int = 1
    page_size: int = 30
    total_pages: int = 1


class HeaderItem(BaseModel):
    name: str
    value: str


class FlagItem(BaseModel):
    id: int
    flag: str
    reason: str | None


class LinkedRequestItem(BaseModel):
    id: int
    method: str
    path: str
    time: str
    direction: str  # "incoming" or "outgoing"


class RequestDetail(BaseModel):
    id: int
    method: str
    path: str
    port: int
    timestamp: datetime
    user_agent: str | None
    body: str | None
    is_blocked: bool
    headers: list[HeaderItem]
    query_params: dict[str, str]
    flags: list[FlagItem]
    linked_requests: list[LinkedRequestItem]


class ResponseDetail(BaseModel):
    id: int | None
    status: int | None
    body: str | None
    headers: list[HeaderItem]
    flags: list[FlagItem]


class RequestDetailResponse(BaseModel):
    request: RequestDetail
    response: ResponseDetail | None


class TimePoint(BaseModel):
    timestamp: int  # Unix timestamp in milliseconds
    count: int


class PathStatItem(BaseModel):
    method: str
    path: str
    total_count: int
    time_series: list[TimePoint]  # Timestamp-count pairs


class PathStatsResponse(BaseModel):
    paths: list[PathStatItem]
    service_name: str
    service_port: int
    ignored_paths: list[str] = []
    window_minutes: int = 60


class QueryStatItem(BaseModel):
    param: str
    value: str
    total_count: int
    time_series: list[TimePoint]


class QueryStatsResponse(BaseModel):
    queries: list[QueryStatItem]
    service_name: str
    service_port: int
    ignored_queries: list[str] = []
    window_minutes: int = 60


class HeaderStatItem(BaseModel):
    name: str
    value: str
    total_count: int
    time_series: list[TimePoint]


class HeaderStatsResponse(BaseModel):
    headers: list[HeaderStatItem]
    service_name: str
    service_port: int
    ignored_headers: list[str] = []
    window_minutes: int = 60


class TCPConnectionItem(BaseModel):
    id: int
    connection_id: int
    timestamp: datetime
    duration_ms: int | None
    bytes_in: int
    bytes_out: int
    flags_in: int
    flags_out: int
    is_blocked: bool


class TCPConnectionListResponse(BaseModel):
    connections: list[TCPConnectionItem]
    total: int
    service_name: str
    service_port: int
    page: int = 1
    page_size: int = 30
    total_pages: int = 1


class TCPEventItem(BaseModel):
    id: int
    timestamp: datetime
    event_type: str
    data_size: int
    data_bytes: str | None  # Base64 encoded bytes
    truncated: bool
    end_stream: bool
    flags: list[str]


class TCPConnectionStatsItem(BaseModel):
    read_min: int
    read_max: int
    write_min: int
    write_max: int
    count: int
    time_series: list[dict[str, int]] = []


class TCPConnectionStatsResponse(BaseModel):
    stats: list[TCPConnectionStatsItem]
    service_name: str
    service_port: int
    precision: int
    window_minutes: int = 60


class TCPConnectionDetail(BaseModel):
    id: int
    connection_id: int
    port: int
    timestamp: datetime
    duration_ms: int | None
    bytes_in: int
    bytes_out: int
    events: list[TCPEventItem]
    total_flags: int
    is_blocked: bool
