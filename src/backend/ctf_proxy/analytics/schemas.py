from pydantic import BaseModel

from ctf_proxy.analytics.preview import HTTP


class RuleInfoModel(BaseModel):
    name: str
    status: str
    port: int | None = None
    error: str | None = None


class RuleListResponse(BaseModel):
    rules: list[RuleInfoModel]


class RuleSourceResponse(BaseModel):
    name: str
    status: str
    port: int | None = None
    source: str


class SaveRuleRequest(BaseModel):
    source: str


class PreviewRequest(BaseModel):
    source: str
    source_type: str = HTTP
    ids: list[int]


class PreviewMatchModel(BaseModel):
    rule: str
    tag: str
    meta: str
    port: int
    ref_id: int


class PreviewResponse(BaseModel):
    matches: list[PreviewMatchModel]
    count: int
    scanned: int


class MessageResponse(BaseModel):
    status: str
    detail: str | None = None


class TagStatItem(BaseModel):
    rule: str
    tag: str
    http_count: int = 0
    tcp_count: int = 0
    total: int = 0


class TagStatsResponse(BaseModel):
    port: int
    tags: list[TagStatItem]


class TagTimePoint(BaseModel):
    timestamp: int
    count: int


class TagTimeSeriesItem(BaseModel):
    rule: str
    tag: str
    total: int
    time_series: list[TagTimePoint]


class TagTimeStatsResponse(BaseModel):
    port: int
    window_minutes: int
    tags: list[TagTimeSeriesItem]


class AnalysisRowModel(BaseModel):
    rule: str
    tag: str
    meta: str | None = None


class AnalysisRowsResponse(BaseModel):
    rows: list[AnalysisRowModel]


class TagsForRefsRequest(BaseModel):
    source_type: str = HTTP
    ids: list[int]
    rules: list[str] | None = None


class TagsForRefsResponse(BaseModel):
    tags: dict[int, list[str]]


class BackfillRequest(BaseModel):
    target_id: int | None = None
    ports: list[int] | None = None


class BackfillJobModel(BaseModel):
    id: int
    target_id: int
    ports: list[int] | None = None
    http_cursor: int
    tcp_cursor: int
    status: str
