from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ctf_proxy.analytics.db import AnalysisDB, make_analysis_db
from ctf_proxy.analytics.preview import HTTP, TCP, PreviewRunner
from ctf_proxy.analytics.rules_store import DRAFT, ENABLED, RulesStore, RuleValidationError
from ctf_proxy.analytics.schemas import (
    AnalysisRowModel,
    AnalysisRowsResponse,
    BackfillJobModel,
    BackfillRequest,
    MessageResponse,
    PreviewMatchModel,
    PreviewRequest,
    PreviewResponse,
    RuleInfoModel,
    RuleListResponse,
    RuleSourceResponse,
    SaveRuleRequest,
    TagsForRefsRequest,
    TagsForRefsResponse,
    TagStatItem,
    TagStatsResponse,
)
from ctf_proxy.analytics.source import SourceReader
from ctf_proxy.db.utils import now_timestamp

store: RulesStore | None = None
preview_runner: PreviewRunner | None = None
analysis_db: AnalysisDB | None = None
source_reader: SourceReader | None = None


def init_app() -> None:
    global store, preview_runner, analysis_db, source_reader
    analysis_db = make_analysis_db()
    store = RulesStore(analysis_db)
    preview_runner = PreviewRunner()
    source_reader = SourceReader()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_app()
    yield


app = FastAPI(title="CTF Proxy Analyzer API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_store() -> RulesStore:
    if store is None:
        raise HTTPException(status_code=500, detail="Analyzer not initialized")
    return store


def require_analysis() -> AnalysisDB:
    if analysis_db is None:
        raise HTTPException(status_code=500, detail="Analyzer not initialized")
    return analysis_db


def require_status(status: str) -> str:
    if status not in (DRAFT, ENABLED):
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    return status


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "backend": "ctf-proxy-analyzer", "version": "1.0.0"}


@app.get("/api/rules", response_model=RuleListResponse)
async def list_rules(port: int | None = None):
    rules = require_store().list_rules(port)
    return RuleListResponse(rules=[RuleInfoModel(**vars(r)) for r in rules])


@app.get("/api/rules/{name}", response_model=RuleSourceResponse)
async def get_rule(name: str, status: str = DRAFT):
    active = require_store()
    require_status(status)
    try:
        source = active.get_source(name, status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    port, _ = active.parse_port(source, name)
    return RuleSourceResponse(name=name, status=status, port=port, source=source)


@app.put("/api/rules/{name}", response_model=MessageResponse)
async def save_rule(name: str, request: SaveRuleRequest):
    try:
        require_store().save_draft(name, request.source)
    except RuleValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return MessageResponse(status="saved", detail=name)


@app.delete("/api/rules/{name}", response_model=MessageResponse)
async def delete_rule(name: str, status: str = DRAFT):
    active = require_store()
    require_status(status)
    try:
        active.delete_rule(name, status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return MessageResponse(status="deleted", detail=name)


@app.post("/api/rules/{name}/promote", response_model=MessageResponse)
async def promote_rule(name: str):
    active = require_store()
    try:
        active.promote(name)
    except RuleValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return MessageResponse(status="promoted", detail=name)


@app.post("/api/preview", response_model=PreviewResponse)
async def preview(request: PreviewRequest):
    if preview_runner is None:
        raise HTTPException(status_code=500, detail="Analyzer not initialized")
    if request.source_type not in (HTTP, TCP):
        raise HTTPException(status_code=400, detail=f"Invalid source_type: {request.source_type}")

    try:
        result = preview_runner.preview(request.source, request.source_type, request.ids)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Rule preview failed: {e}") from e

    return PreviewResponse(
        matches=[PreviewMatchModel(**vars(m)) for m in result.matches],
        count=len(result.matches),
        scanned=result.scanned,
    )


@app.get("/api/tag-stats", response_model=TagStatsResponse)
async def tag_stats(port: int, window_minutes: int = 60):
    db = require_analysis()
    since = now_timestamp() - window_minutes * 60_000
    stats = db.tag_stats(port)
    series = {(s["rule"], s["tag"]): s["time_series"] for s in db.tag_time_series(port, since)}
    tags = [TagStatItem(**s, time_series=series.get((s["rule"], s["tag"]), [])) for s in stats]
    return TagStatsResponse(port=port, window_minutes=window_minutes, tags=tags)


@app.get("/api/analysis/for-ref", response_model=AnalysisRowsResponse)
async def analysis_for_ref(ref_id: int, source_type: str = HTTP):
    source = "http" if source_type != TCP else "tcp"
    rows = require_analysis().analysis_for_ref(source, ref_id)
    return AnalysisRowsResponse(rows=[AnalysisRowModel(**r) for r in rows])


@app.post("/api/tags/for-refs", response_model=TagsForRefsResponse)
async def tags_for_refs(request: TagsForRefsRequest):
    source = "http" if request.source_type != TCP else "tcp"
    tags = require_analysis().tags_for_refs(source, request.ids, request.rules)
    return TagsForRefsResponse(tags=tags)


def job_model(job) -> BackfillJobModel:
    return BackfillJobModel(
        id=job.id,
        target_id=job.target_id,
        ports=job.ports,
        http_cursor=job.http_cursor,
        tcp_cursor=job.tcp_cursor,
        status=job.status,
    )


@app.post("/api/backfill", response_model=BackfillJobModel)
async def create_backfill(request: BackfillRequest):
    db = require_analysis()
    target_id = request.target_id
    if target_id is None:
        if source_reader is None:
            raise HTTPException(status_code=500, detail="Analyzer not initialized")
        target_id = source_reader.max_source_id()
    with db.connect() as conn:
        tx = conn.cursor()
        db.backfill.create(tx, target_id, request.ports, now_timestamp())
        conn.commit()
        job = db.backfill.active(tx)
    return job_model(job)


@app.get("/api/backfill", response_model=BackfillJobModel | None)
async def get_backfill():
    db = require_analysis()
    with db.connect() as conn:
        job = db.backfill.latest(conn.cursor())
    return job_model(job) if job else None
