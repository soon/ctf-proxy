import csv
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from io import StringIO
from pathlib import Path

import httpx
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ctf_proxy.analytics.schemas import (
    BackfillJobModel,
    BackfillRequest,
    MessageResponse,
    PreviewRequest,
    PreviewResponse,
    RuleListResponse,
    RuleSourceResponse,
    SaveRuleRequest,
    TagStatsResponse,
)
from ctf_proxy.common import Config
from ctf_proxy.dashboard.models import (
    FlagItem,
    FlagTimeStatsItem,
    FlagTimeStatsResponse,
    HeaderItem,
    HeaderStatItem,
    HeaderStatsResponse,
    LinkedRequestItem,
    PathStatItem,
    PathStatsResponse,
    QueryStatItem,
    QueryStatsResponse,
    RequestDetail,
    RequestDetailResponse,
    RequestListItem,
    RequestListResponse,
    RequestTimeStatsItem,
    RequestTimeStatsResponse,
    ResponseDetail,
    RuleTagItem,
    ServiceListItem,
    ServiceListResponse,
    TCPConnectionDetail,
    TCPConnectionItem,
    TCPConnectionListResponse,
    TCPConnectionStatsItem,
    TCPConnectionStatsResponse,
    TCPEventItem,
    TCPStats,
    WebSocketConnectionDetail,
    WebSocketConnectionItem,
    WebSocketConnectionListResponse,
    WebSocketFrame,
    WebSocketFrameItem,
)
from ctf_proxy.dashboard.models import (
    ServiceStats as ServiceStatsModel,
)
from ctf_proxy.dashboard.stats import (
    HeaderStats,
    PathStats,
    QueryParamStats,
    ServiceStats,
    fetch_raw_request,
)
from ctf_proxy.db import ProxyStatsDB
from ctf_proxy.db.dashboard_queries import DashboardQueries
from ctf_proxy.db.utils import convert_timestamp_to_datetime

config: Config | None = None
db: ProxyStatsDB | None = None
queries: DashboardQueries | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os

    try:
        # Use environment variables if set (for Gunicorn/Docker mode)
        config_path = os.environ.get(
            "CONFIG_PATH", os.environ.get("CTF_CONFIG_PATH", "../config.yml")
        )
        init_app(config_path)
    except FileNotFoundError as e:
        print(f"Warning: {e}")
        print("Server will start but endpoints will return errors until properly initialized")
    yield
    if config:
        config.stop_watching()


app = FastAPI(title="CTF Proxy Dashboard API", version="1.0.0", lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def init_app(config_path: str = "config.yml") -> None:
    global config, db, queries

    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    config = Config(config_file)
    config.start_watching()
    db = ProxyStatsDB()
    queries = DashboardQueries()


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "backend": "ctf-proxy-dashboard",
        "version": "1.0.0",
    }


@app.post("/api/sql")
async def execute_sql(request: dict):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    query = request.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    timeout = request.get("timeout", 10.0)
    if timeout:
        try:
            timeout = float(timeout)
            if timeout <= 0 or timeout > 60:
                raise ValueError("Timeout must be between 0 and 60 seconds")
        except (TypeError, ValueError):
            timeout = 10.0

    try:
        result = db.execute_sql(query, timeout=timeout)
        return {"rows": result.rows, "count": len(result.rows), "query_time": result.query_time_ms}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except TimeoutError as e:
        raise HTTPException(status_code=408, detail=str(e)) from e
    except psycopg.Error as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/sql/schema")
async def get_sql_schema():
    schema_path = Path(__file__).parent.parent / "db" / "schema.sql"

    try:
        with open(schema_path) as f:
            schema_content = f.read()
        return {"schema": schema_content}
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail="Schema file not found") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading schema: {str(e)}") from e


@app.post("/api/sql/export")
async def export_sql_csv(request: dict):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    query = request.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    timeout = request.get("timeout", 10.0)
    if timeout:
        try:
            timeout = float(timeout)
            if timeout <= 0 or timeout > 60:
                raise ValueError("Timeout must be between 0 and 60 seconds")
        except (TypeError, ValueError):
            timeout = 10.0

    try:
        result = db.execute_sql(query, default_limit=10000, timeout=timeout)

        if not result.rows:
            raise HTTPException(status_code=404, detail="No data to export")

        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=result.columns)
        writer.writeheader()
        writer.writerows(result.rows)

        output.seek(0)

        return StreamingResponse(
            iter([output.read()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except TimeoutError as e:
        raise HTTPException(status_code=408, detail=str(e)) from e
    except psycopg.Error as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def get_all_services_stats_optimized(ports: list[int], db_instance) -> dict:
    """Fetch stats for all services in optimized batch queries."""
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    with db_instance.connect() as conn:
        cursor = conn.cursor()

        five_minutes_ago = int(time.time() * 1000) - (5 * 60 * 1000)

        # 1. Get service stats for all ports at once
        start = time.time()
        service_stats = {row[0]: row[1:] for row in queries.service_stats_by_ports(cursor, ports)}
        logger.info(f"Query 1 (service_stats): {time.time() - start:.3f}s")

        # 2. Get response code stats for all ports
        start = time.time()
        response_codes = {}
        for port, status_code, count in queries.response_code_stats_by_ports(cursor, ports):
            if port not in response_codes:
                response_codes[port] = {}
            response_codes[port][status_code] = count
        logger.info(f"Query 2 (response_codes): {time.time() - start:.3f}s")

        # 3. Skip unique paths count - too slow with large datasets
        unique_paths = {}

        # 4. Skip header stats - too slow with large datasets
        header_stats = {}

        # 7. Skip TCP stats for now - tcp_stats table is not populated
        tcp_stats = {}

        # 8. Get request count delta for last 5 minutes using stats table
        start = time.time()
        request_deltas = dict(queries.request_count_deltas(cursor, ports, five_minutes_ago))
        logger.info(f"Query 8 (request_deltas): {time.time() - start:.3f}s")

        # 9. Get blocked request count delta for last 5 minutes using stats table
        start = time.time()
        blocked_request_deltas = dict(
            queries.blocked_request_count_deltas(cursor, ports, five_minutes_ago)
        )
        logger.info(f"Query 9 (blocked_request_deltas): {time.time() - start:.3f}s")

        # 10. Get flag deltas for last 5 minutes
        start = time.time()
        flag_deltas = {}
        for row in queries.flag_deltas_by_ports(cursor, ports, five_minutes_ago):
            port, written, retrieved = row
            flag_deltas[port] = (written or 0, retrieved or 0)
        logger.info(f"Query 10 (flag_deltas): {time.time() - start:.3f}s")

        # Combine all stats
        result = {}
        for port in ports:
            service_data = service_stats.get(port, (0, 0, 0, 0, 0, 0, 0))
            status_counts = response_codes.get(port, {})

            error_responses = sum(count for status, count in status_counts.items() if status >= 400)
            success_responses = sum(
                count for status, count in status_counts.items() if 200 <= status < 300
            )
            redirect_responses = sum(
                count for status, count in status_counts.items() if 300 <= status < 400
            )

            header_data = header_stats.get(port, (0, 0))
            tcp_raw_data = tcp_stats.get(port)
            tcp_data = None
            if tcp_raw_data:
                tcp_data = {
                    "total_connections": tcp_raw_data[0],
                    "total_bytes_in": tcp_raw_data[1],
                    "total_bytes_out": tcp_raw_data[2],
                    "avg_duration_ms": int(tcp_raw_data[3]),
                    "total_flags_found": tcp_raw_data[4],
                }
            flag_delta_data = flag_deltas.get(port, (0, 0))

            result[port] = {
                "total_requests": service_data[0],
                "blocked_requests": service_data[1],
                "total_responses": service_data[2],
                "blocked_responses": service_data[3],
                "requests_delta": request_deltas.get(port, 0),
                "blocked_requests_delta": blocked_request_deltas.get(port, 0),
                "flags_written": service_data[4],
                "flags_retrieved": service_data[5],
                "flags_blocked": service_data[6],
                "total_flags": service_data[4] + service_data[5],
                "flags_written_delta": flag_delta_data[0],
                "flags_retrieved_delta": flag_delta_data[1],
                "status_counts": status_counts,
                "error_responses": error_responses,
                "success_responses": success_responses,
                "redirect_responses": redirect_responses,
                "unique_paths": unique_paths.get(port, 0),
                "unique_headers": header_data[0],
                "unique_header_values": header_data[1],
                "tcp_stats": tcp_data,
            }

        return result


@app.get("/api/services", response_model=ServiceListResponse)
async def get_services() -> ServiceListResponse:
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    # Get all ports from config
    ports = [service.port for service in config.services]

    # Fetch all stats in optimized batch queries
    all_stats = get_all_services_stats_optimized(ports, db)

    services = []
    for service in config.services:
        stats = all_stats.get(service.port, {})

        tcp_stats = None
        if service.type.value == "tcp" and stats.get("tcp_stats"):
            tcp_data = stats["tcp_stats"]
            tcp_stats = TCPStats(
                total_connections=tcp_data["total_connections"],
                total_bytes_in=tcp_data["total_bytes_in"],
                total_bytes_out=tcp_data["total_bytes_out"],
                avg_duration_ms=tcp_data["avg_duration_ms"],
                total_flags_found=tcp_data["total_flags_found"],
            )

        stats_model = ServiceStatsModel(
            total_requests=stats.get("total_requests", 0),
            blocked_requests=stats.get("blocked_requests", 0),
            total_responses=stats.get("total_responses", 0),
            blocked_responses=stats.get("blocked_responses", 0),
            requests_delta=stats.get("requests_delta", 0),
            blocked_requests_delta=stats.get("blocked_requests_delta", 0),
            error_responses=stats.get("error_responses", 0),
            success_responses=stats.get("success_responses", 0),
            redirect_responses=stats.get("redirect_responses", 0),
            status_counts=stats.get("status_counts", {}),
            unique_paths=stats.get("unique_paths", 0),
            flags_written=stats.get("flags_written", 0),
            flags_retrieved=stats.get("flags_retrieved", 0),
            flags_blocked=stats.get("flags_blocked", 0),
            total_flags=stats.get("total_flags", 0),
            flags_written_delta=stats.get("flags_written_delta", 0),
            flags_retrieved_delta=stats.get("flags_retrieved_delta", 0),
            unique_headers=stats.get("unique_headers", 0),
            unique_header_values=stats.get("unique_header_values", 0),
            tcp_stats=tcp_stats,
        )

        service_item = ServiceListItem(
            name=service.name,
            port=service.port,
            type=service.type.value,
            stats=stats_model,
        )

        services.append(service_item)

    return ServiceListResponse(services=services, timestamp=datetime.now())


@app.get("/api/services/{port}", response_model=ServiceListItem)
async def get_service_by_port(port: int) -> ServiceListItem:
    import logging

    logger = logging.getLogger(__name__)

    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    service = config.get_service_by_port(port)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service not found on port {port}")

    start = time.time()
    stats_obj = ServiceStats(service.port, db)
    current_stats = stats_obj.get_current_stats()
    logger.info(f"get_current_stats took {time.time() - start:.3f}s")

    five_minutes_ago = int(time.time() * 1000) - (5 * 60 * 1000)

    with db.connect() as conn:
        cursor = conn.cursor()

        # Use stats table instead of raw http_request table
        start = time.time()
        requests_delta = (
            queries.request_count_delta_for_port(cursor, service.port, five_minutes_ago)[0] or 0
        )
        logger.info(f"requests_delta query took {time.time() - start:.3f}s")

        start = time.time()
        blocked_requests_delta = (
            queries.blocked_request_count_delta_for_port(cursor, service.port, five_minutes_ago)[0]
            or 0
        )
        logger.info(f"blocked_requests_delta query took {time.time() - start:.3f}s")

        start = time.time()
        flag_delta_result = queries.flag_delta_for_port(cursor, service.port, five_minutes_ago)
        flags_written_delta = flag_delta_result[0] or 0
        flags_retrieved_delta = flag_delta_result[1] or 0
        logger.info(f"flag_delta query took {time.time() - start:.3f}s")

    tcp_stats = None
    if service.type.value == "tcp" and current_stats.get("tcp_stats"):
        tcp_data = current_stats["tcp_stats"]
        tcp_stats = TCPStats(
            total_connections=tcp_data["total_connections"],
            total_bytes_in=tcp_data["total_bytes_in"],
            total_bytes_out=tcp_data["total_bytes_out"],
            avg_duration_ms=tcp_data["avg_duration_ms"],
            total_flags_found=tcp_data["total_flags_found"],
        )

    stats_model = ServiceStatsModel(
        total_requests=current_stats["total_requests"],
        blocked_requests=current_stats["blocked_requests"],
        total_responses=current_stats["total_responses"],
        blocked_responses=current_stats["blocked_responses"],
        requests_delta=requests_delta,
        blocked_requests_delta=blocked_requests_delta,
        error_responses=current_stats["error_responses"],
        success_responses=current_stats["success_responses"],
        redirect_responses=current_stats["redirect_responses"],
        status_counts=current_stats["status_counts"],
        unique_paths=current_stats["unique_paths"],
        flags_written=current_stats["flags_written"],
        flags_retrieved=current_stats["flags_retrieved"],
        flags_blocked=current_stats["flags_blocked"],
        total_flags=current_stats["total_flags"],
        flags_written_delta=flags_written_delta,
        flags_retrieved_delta=flags_retrieved_delta,
        unique_headers=current_stats["unique_headers"],
        unique_header_values=current_stats["unique_header_values"],
        tcp_stats=tcp_stats,
    )

    return ServiceListItem(
        name=service.name,
        port=service.port,
        type=service.type.value,
        stats=stats_model,
    )


@app.get("/api/services/{port}/requests", response_model=RequestListResponse)
async def get_service_requests(
    port: int,
    page: int = 1,
    page_size: int = 30,
    filter_path: str | None = None,
    filter_method: str | None = None,
    filter_status: int | None = None,
    filter_blocked: bool | None = None,
    filter_tag: str | None = None,
    visible_rules: str | None = None,
) -> RequestListResponse:
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    service = config.get_service_by_port(port)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service not found on port {port}")

    requests = []

    with db.connect() as conn:
        offset = (page - 1) * page_size

        total_count, rows = queries.list_http_requests(
            conn,
            port,
            filter_path,
            filter_method,
            filter_status,
            filter_blocked,
            filter_tag,
            page_size,
            offset,
        )

        for row in rows:
            (
                req_id,
                start_time,
                method,
                path,
                status,
                is_blocked,
                user_agent,
                req_flags,
                resp_flags,
                total_session_requests,
            ) = row

            # Convert timestamp
            timestamp = convert_timestamp_to_datetime(start_time) if start_time else datetime.now()

            requests.append(
                RequestListItem(
                    id=req_id,
                    timestamp=timestamp,
                    method=method,
                    path=path,
                    status=status,
                    is_blocked=bool(is_blocked),
                    user_agent=user_agent or "",
                    request_flags=req_flags or 0,
                    response_flags=resp_flags or 0,
                    total_links=total_session_requests or 0,
                )
            )

    tag_map = await fetch_tags_for_refs("http", [item.id for item in requests], visible_rules)
    for item in requests:
        item.tags = tag_map.get(item.id, [])

    return RequestListResponse(
        requests=requests,
        total=total_count,
        service_name=service.name,
        service_port=port,
        page=page,
        page_size=page_size,
        total_pages=(total_count + page_size - 1) // page_size,
    )


@app.get("/api/requests/{request_id}", response_model=RequestDetailResponse)
async def get_request_detail(request_id: int) -> RequestDetailResponse:
    if db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    with db.connect() as conn:
        cursor = conn.cursor()

        # Get request data
        row = queries.http_request_detail(cursor, request_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Request not found: {request_id}")

        (
            method,
            path,
            body,
            user_agent,
            start_time,
            port,
            is_blocked,
            is_websocket,
            response_id,
            status,
            response_body,
        ) = row

        # Parse query parameters from path
        query_params = {}
        if "?" in path:
            path_part, query_string = path.split("?", 1)
            for param in query_string.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    query_params[key] = value
                else:
                    query_params[param] = ""
        else:
            path_part = path

        # Get request headers
        request_headers = [
            HeaderItem(name=name, value=value)
            for name, value in queries.http_request_headers(cursor, request_id)
        ]

        # Get request flags
        request_flags = [
            FlagItem(id=id, flag=value, location=location)
            for id, value, location in queries.flags_for_request(cursor, request_id)
        ]

        # Get linked requests
        linked_requests = []

        # Get all requests in the same session with session key
        linked_info = queries.linked_session_requests(cursor, request_id)
        incoming_ids = [row[0] for row in linked_info if row[1] == "incoming"]
        outgoing_ids = [row[0] for row in linked_info if row[1] == "outgoing"]
        session_key = linked_info[0][2] if linked_info else None

        # Get info for all linked requests
        all_linked_ids = incoming_ids + outgoing_ids
        if all_linked_ids:
            for req_id, link_method, link_path, link_start_time in queries.http_requests_basic(
                cursor, all_linked_ids
            ):
                # Parse path
                if "?" in link_path:
                    link_path_part, _ = link_path.split("?", 1)
                else:
                    link_path_part = link_path

                # Convert timestamp
                link_timestamp = (
                    convert_timestamp_to_datetime(link_start_time)
                    if link_start_time
                    else datetime.now()
                )

                direction = "incoming" if req_id in incoming_ids else "outgoing"
                linked_requests.append(
                    LinkedRequestItem(
                        id=req_id,
                        method=link_method,
                        path=link_path_part,
                        time=link_timestamp.strftime("%H:%M:%S"),
                        direction=direction,
                        session_key=session_key,
                    )
                )

        # Convert timestamp
        timestamp = convert_timestamp_to_datetime(start_time) if start_time else datetime.now()

        # Get WebSocket frames if this is a WebSocket request
        websocket_frames = []
        if is_websocket:
            ws_conn_row = queries.websocket_connection_id_for_request(cursor, request_id)
            if ws_conn_row:
                ws_connection_id = ws_conn_row[0]
                for frame_row in queries.websocket_frames_for_connection(cursor, ws_connection_id):
                    frame_id, ord_num, opcode, payload_text, payload_size, is_client = frame_row

                    frame_flags = [
                        f[0] for f in queries.flags_for_websocket_frame(cursor, frame_id)
                    ]

                    websocket_frames.append(
                        WebSocketFrame(
                            id=frame_id,
                            ord=ord_num,
                            opcode=opcode,
                            payload_text=payload_text,
                            payload_size=payload_size,
                            is_client=bool(is_client),
                            flags=frame_flags,
                        )
                    )

        request_detail = RequestDetail(
            id=request_id,
            method=method,
            path=path_part,
            port=port,
            timestamp=timestamp,
            user_agent=user_agent,
            body=body,
            is_blocked=bool(is_blocked),
            headers=request_headers,
            query_params=query_params,
            flags=request_flags,
            linked_requests=linked_requests,
            is_websocket=bool(is_websocket),
            websocket_frames=websocket_frames,
        )

        # Build response detail if exists
        response_detail = None
        if response_id:
            # Get response headers
            response_headers = [
                HeaderItem(name=name, value=value)
                for name, value in queries.http_response_headers(cursor, response_id)
            ]

            # Get response flags
            response_flags = [
                FlagItem(id=id, flag=value, location=location)
                for id, value, location in queries.flags_for_response(cursor, response_id)
            ]

            response_detail = ResponseDetail(
                id=response_id,
                status=status,
                body=response_body,
                headers=response_headers,
                flags=response_flags,
            )

    request_detail.tags = await fetch_analysis_rows("http", request_id)

    return RequestDetailResponse(request=request_detail, response=response_detail)


@app.get("/api/requests/{request_id}/raw")
async def get_request_raw(request_id: int):
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    try:
        raw_data = fetch_raw_request(request_id, db)
        if raw_data:
            return raw_data
        else:
            raise HTTPException(status_code=404, detail="Raw request data not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/services/{port}/paths", response_model=PathStatsResponse)
async def get_service_path_stats(
    port: int,
    window_minutes: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> PathStatsResponse:
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    service = config.get_service_by_port(port)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service not found on port {port}")

    path_stats = PathStats(db)

    # Use custom time range if provided, otherwise use window_minutes
    if start_time and end_time:
        from datetime import datetime

        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        path_time_data = path_stats.get_time_series_for_range(port, start_dt, end_dt)
        actual_window = int((end_dt - start_dt).total_seconds() / 60)
    else:
        window = window_minutes or 60
        path_time_data = path_stats.get_time_series_with_totals(port, window)
        actual_window = window

    paths = []
    for (method, path), data in path_time_data.items():
        # time_series is already a list of dicts with timestamp and count
        paths.append(
            PathStatItem(
                method=method,
                path=path,
                total_count=data["total_count"],
                time_series=data["time_series"],
            )
        )

    ignored_paths = []
    if service.ignore_path_stats:
        for ignored_path in service.ignore_path_stats:
            ignored_paths.append(f"{ignored_path.method} {ignored_path.path}")

    return PathStatsResponse(
        paths=paths,
        service_name=service.name,
        service_port=port,
        ignored_paths=ignored_paths,
        window_minutes=actual_window,
    )


@app.get("/api/services/{port}/queries", response_model=QueryStatsResponse)
async def get_service_query_stats(
    port: int,
    window_minutes: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> QueryStatsResponse:
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    service = config.get_service_by_port(port)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service not found on port {port}")

    query_stats = QueryParamStats(db)

    if start_time and end_time:
        from datetime import datetime

        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        query_time_data = query_stats.get_time_series_for_range(port, start_dt, end_dt)
        actual_window = int((end_dt - start_dt).total_seconds() / 60)
    else:
        window = window_minutes or 60
        query_time_data = query_stats.get_time_series_with_totals(port, window)
        actual_window = window

    queries = []
    for (param, value), data in query_time_data.items():
        queries.append(
            QueryStatItem(
                param=param,
                value=value,
                total_count=data["total_count"],
                time_series=data["time_series"],
            )
        )

    ignored_queries = []
    if service.ignore_query_param_stats:
        # ignore_query_param_stats is a dict[str, str], format as "param=value"
        for param, value in service.ignore_query_param_stats.items():
            ignored_queries.append(f"{param}={value}")

    return QueryStatsResponse(
        queries=queries,
        service_name=service.name,
        service_port=port,
        ignored_queries=ignored_queries,
        window_minutes=actual_window,
    )


@app.get("/api/services/{port}/headers", response_model=HeaderStatsResponse)
async def get_service_header_stats(
    port: int,
    window_minutes: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> HeaderStatsResponse:
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    service = config.get_service_by_port(port)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service not found on port {port}")

    header_stats = HeaderStats(db)

    if start_time and end_time:
        from datetime import datetime

        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        header_time_data = header_stats.get_time_series_for_range(port, start_dt, end_dt)
        actual_window = int((end_dt - start_dt).total_seconds() / 60)
    else:
        window = window_minutes or 60
        header_time_data = header_stats.get_time_series_with_totals(port, window)
        actual_window = window

    headers = []
    for (name, value), data in header_time_data.items():
        headers.append(
            HeaderStatItem(
                name=name,
                value=value,
                total_count=data["total_count"],
                time_series=data["time_series"],
            )
        )

    ignored_headers = []
    if service.ignore_header_stats:
        # ignore_header_stats is a dict[str, str]
        ignored_headers = list(service.ignore_header_stats.keys())

    return HeaderStatsResponse(
        headers=headers,
        service_name=service.name,
        service_port=port,
        ignored_headers=ignored_headers,
        window_minutes=actual_window,
    )


def get_tcp_stats_for_port(port: int) -> TCPStats | None:
    if db is None:
        return None

    with db.connect() as conn:
        cursor = conn.cursor()
        row = queries.tcp_stats_for_port(cursor, port)
        if not row:
            return TCPStats(
                total_connections=0,
                total_bytes_in=0,
                total_bytes_out=0,
                avg_duration_ms=0,
                total_flags_found=0,
            )

        return TCPStats(
            total_connections=row[0],
            total_bytes_in=row[1],
            total_bytes_out=row[2],
            avg_duration_ms=row[3],
            total_flags_found=row[4],
        )


@app.get("/api/services/{port}/tcp-connections", response_model=TCPConnectionListResponse)
async def get_tcp_connections(
    port: int,
    page: int = 1,
    page_size: int = 30,
    search: str | None = None,
    filter_tag: str | None = None,
    visible_rules: str | None = None,
) -> TCPConnectionListResponse:
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    service = config.get_service_by_port(port)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service not found on port {port}")

    if service.type.value != "tcp":
        raise HTTPException(status_code=400, detail=f"Service on port {port} is not a TCP service")

    offset = (page - 1) * page_size

    search = search.strip() if search else None

    with db.connect() as conn:
        total, rows = queries.list_tcp_connections(
            conn, port, search, filter_tag, page_size, offset
        )

        connections = []
        for row in rows:
            connections.append(
                TCPConnectionItem(
                    id=row[0],
                    connection_id=row[1],
                    timestamp=datetime.fromtimestamp(row[2] / 1000),
                    duration_ms=row[3],
                    bytes_in=row[4],
                    bytes_out=row[5],
                    flags_in=row[6],
                    flags_out=row[7],
                    is_blocked=bool(row[8]),
                )
            )

    tag_map = await fetch_tags_for_refs("tcp", [c.id for c in connections], visible_rules)
    for c in connections:
        c.tags = tag_map.get(c.id, [])

    total_pages = (total + page_size - 1) // page_size

    return TCPConnectionListResponse(
        connections=connections,
        total=total,
        service_name=service.name,
        service_port=port,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@app.get("/api/tcp-connections/{connection_id}", response_model=TCPConnectionDetail)
async def get_tcp_connection_detail(connection_id: int) -> TCPConnectionDetail:
    if db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    with db.connect() as conn:
        cursor = conn.cursor()

        row = queries.tcp_connection_detail(cursor, connection_id)
        if not row:
            raise HTTPException(
                status_code=404, detail=f"TCP connection not found: {connection_id}"
            )

        events = []
        for event_row in queries.tcp_events_for_connection(cursor, connection_id):
            event_id = event_row[0]

            flags = [f[0] for f in queries.flags_for_tcp_event(cursor, event_id)]

            # Convert binary data to base64 if present
            data_bytes = None
            if event_row[4] is not None:
                import base64

                data_bytes = base64.b64encode(event_row[4]).decode("ascii")

            events.append(
                TCPEventItem(
                    id=event_id,
                    timestamp=datetime.fromtimestamp(event_row[1] / 1000),
                    event_type=event_row[2],
                    data_size=event_row[3],
                    data_bytes=data_bytes,
                    truncated=bool(event_row[5]),
                    end_stream=bool(event_row[6]),
                    flags=flags,
                )
            )

        total_flags = queries.flag_count_for_tcp_connection(cursor, connection_id)[0]

        return TCPConnectionDetail(
            id=row[0],
            connection_id=row[1],
            port=row[2],
            timestamp=datetime.fromtimestamp(row[3] / 1000),
            duration_ms=row[4],
            bytes_in=row[5],
            bytes_out=row[6],
            events=events,
            total_flags=total_flags,
            is_blocked=bool(row[7]),
        )


@app.get("/api/services/{port}/tcp-connection-stats", response_model=TCPConnectionStatsResponse)
def get_tcp_connection_stats(port: int, window_minutes: int = 60) -> TCPConnectionStatsResponse:
    service = config.get_service_by_port(port)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service not found on port {port}")

    from datetime import datetime, timedelta

    now = datetime.now()
    start_time = now - timedelta(minutes=window_minutes)
    start_timestamp = int(start_time.timestamp() * 1000)

    precision = service.tcp_connection_stats_precision

    with db.connect() as conn:
        cursor = conn.cursor()

        # Get time-based stats for the window
        # Group by byte ranges and create time series
        stats_map = {}
        for row in queries.tcp_connection_time_stats(cursor, port, start_timestamp):
            read_min, read_max, write_min, write_max, time, count = row
            key = (read_min, read_max, write_min, write_max)

            if key not in stats_map:
                stats_map[key] = {"total_count": 0, "blocked_count": 0, "time_points": []}

            stats_map[key]["total_count"] += count
            stats_map[key]["time_points"].append({"timestamp": time, "count": count})

        # Get blocked counts for each byte range pattern
        # Map blocked counts to the corresponding ranges
        for row in queries.tcp_connection_blocked_counts(cursor, port, start_timestamp):
            bytes_in, bytes_out, blocked_count = row
            # Find the matching range in stats_map
            for (read_min, read_max, write_min, write_max), data in stats_map.items():
                if read_min <= bytes_in <= read_max and write_min <= bytes_out <= write_max:
                    data["blocked_count"] += blocked_count
                    break

        # Convert to response format
        stats = []
        for (read_min, read_max, write_min, write_max), data in stats_map.items():
            stats.append(
                TCPConnectionStatsItem(
                    read_min=read_min,
                    read_max=read_max,
                    write_min=write_min,
                    write_max=write_max,
                    count=data["total_count"],
                    blocked_count=data["blocked_count"],
                    time_series=data["time_points"],
                )
            )

    return TCPConnectionStatsResponse(
        stats=stats,
        service_name=service.name,
        service_port=port,
        precision=precision,
        window_minutes=window_minutes,
    )


@app.get(
    "/api/services/{port}/websocket-connections", response_model=WebSocketConnectionListResponse
)
async def get_websocket_connections(
    port: int,
    page: int = 1,
    page_size: int = 30,
) -> WebSocketConnectionListResponse:
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    service = config.get_service_by_port(port)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service not found on port {port}")

    offset = (page - 1) * page_size

    with db.connect() as conn:
        cursor = conn.cursor()

        total, rows = queries.list_websocket_connections(cursor, port, page_size, offset)

        connections = []
        for row in rows:
            connections.append(
                WebSocketConnectionItem(
                    id=row[0],
                    timestamp=datetime.fromtimestamp(row[1] / 1000),
                    duration_ms=row[2],
                    frames_in=row[3],
                    frames_out=row[4],
                    bytes_in=row[5],
                    bytes_out=row[6],
                    flags_in=row[7],
                    flags_out=row[8],
                    is_blocked=bool(row[9]),
                )
            )

    total_pages = (total + page_size - 1) // page_size

    return WebSocketConnectionListResponse(
        connections=connections,
        total=total,
        service_name=service.name,
        service_port=port,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@app.get("/api/websocket-connections/{connection_id}", response_model=WebSocketConnectionDetail)
async def get_websocket_connection_detail(connection_id: int) -> WebSocketConnectionDetail:
    if db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    with db.connect() as conn:
        cursor = conn.cursor()

        row = queries.websocket_connection_detail(cursor, connection_id)
        if not row:
            raise HTTPException(
                status_code=404, detail=f"WebSocket connection not found: {connection_id}"
            )

        frames = []
        for frame_row in queries.websocket_frames_detail(cursor, connection_id):
            frame_id = frame_row[0]

            flags = [f[0] for f in queries.flags_for_websocket_frame(cursor, frame_id)]

            frames.append(
                WebSocketFrameItem(
                    id=frame_id,
                    timestamp=datetime.fromtimestamp(frame_row[1] / 1000),
                    direction=frame_row[2],
                    opcode=frame_row[3],
                    payload_size=frame_row[4],
                    payload_text=frame_row[5],
                    flags=flags,
                )
            )

        total_flags = queries.flag_count_for_websocket_connection(cursor, connection_id)[0]

        return WebSocketConnectionDetail(
            id=row[0],
            port=row[1],
            timestamp=datetime.fromtimestamp(row[2] / 1000),
            duration_ms=row[3],
            frames_in=row[4],
            frames_out=row[5],
            bytes_in=row[6],
            bytes_out=row[7],
            frames=frames,
            total_flags=total_flags,
            is_blocked=bool(row[8]),
        )


@app.get("/api/flags/recent", response_model=FlagTimeStatsResponse)
def get_recent_flag_stats() -> FlagTimeStatsResponse:
    """Get flag statistics for the last 5 minutes."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    five_minutes_ago = int(time.time() * 1000) - (5 * 60 * 1000)

    with db.connect() as conn:
        cursor = conn.cursor()

        stats = []
        for row in queries.recent_flag_stats(cursor, five_minutes_ago):
            port, time_ms, write_count, read_count = row
            stats.append(
                FlagTimeStatsItem(
                    port=port,
                    time=convert_timestamp_to_datetime(time_ms),
                    write_count=write_count,
                    read_count=read_count,
                    total_count=write_count + read_count,
                )
            )

        return FlagTimeStatsResponse(stats=stats, window_minutes=5)


@app.get("/api/services/{port}/flag-time-stats", response_model=FlagTimeStatsResponse)
def get_service_flag_time_stats(port: int, window_minutes: int = 60) -> FlagTimeStatsResponse:
    """Get flag statistics for a specific service."""
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    service = config.get_service_by_port(port)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service not found on port {port}")

    start_time = int(time.time() * 1000) - (window_minutes * 60 * 1000)

    with db.connect() as conn:
        cursor = conn.cursor()

        stats = []
        for row in queries.flag_time_stats_for_port(cursor, port, start_time):
            port, time_ms, write_count, read_count = row
            stats.append(
                FlagTimeStatsItem(
                    port=port,
                    time=convert_timestamp_to_datetime(time_ms),
                    write_count=write_count,
                    read_count=read_count,
                    total_count=write_count + read_count,
                )
            )

        return FlagTimeStatsResponse(stats=stats, window_minutes=window_minutes)


@app.get("/api/services/{port}/request-time-stats", response_model=RequestTimeStatsResponse)
def get_service_request_time_stats(port: int, window_minutes: int = 60) -> RequestTimeStatsResponse:
    """Get request statistics for a specific service."""
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    service = config.get_service_by_port(port)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service not found on port {port}")

    if service.type.value == "tcp":
        raise HTTPException(status_code=400, detail="Request stats not available for TCP services")

    start_time = int(time.time() * 1000) - (window_minutes * 60 * 1000)

    with db.connect() as conn:
        cursor = conn.cursor()

        stats = []
        for row in queries.request_time_stats_for_port(cursor, port, start_time):
            port, time_ms, count, blocked_count = row
            stats.append(
                RequestTimeStatsItem(
                    port=port,
                    time=convert_timestamp_to_datetime(time_ms),
                    count=count,
                    blocked_count=blocked_count,
                )
            )

        return RequestTimeStatsResponse(stats=stats, window_minutes=window_minutes)


@app.get("/api/request-time-stats", response_model=RequestTimeStatsResponse)
def get_all_request_time_stats(window_minutes: int = 60) -> RequestTimeStatsResponse:
    """Get request statistics for all services."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    start_time = int(time.time() * 1000) - (window_minutes * 60 * 1000)

    with db.connect() as conn:
        cursor = conn.cursor()

        stats = []
        for row in queries.all_request_time_stats(cursor, start_time):
            port, time_ms, count, blocked_count = row
            stats.append(
                RequestTimeStatsItem(
                    port=port,
                    time=convert_timestamp_to_datetime(time_ms),
                    count=count,
                    blocked_count=blocked_count,
                )
            )

        return RequestTimeStatsResponse(stats=stats, window_minutes=window_minutes)


@app.get("/api/flag-time-stats", response_model=FlagTimeStatsResponse)
def get_all_flag_time_stats(window_minutes: int = 60) -> FlagTimeStatsResponse:
    """Get flag statistics for all services."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    start_time = int(time.time() * 1000) - (window_minutes * 60 * 1000)

    with db.connect() as conn:
        cursor = conn.cursor()

        stats = []
        for row in queries.all_flag_time_stats(cursor, start_time):
            port, time_ms, write_count, read_count = row
            stats.append(
                FlagTimeStatsItem(
                    port=port,
                    time=convert_timestamp_to_datetime(time_ms),
                    write_count=write_count,
                    read_count=read_count,
                    total_count=write_count + read_count,
                )
            )

        return FlagTimeStatsResponse(stats=stats, window_minutes=window_minutes)


# Config management models
class ConfigContent(BaseModel):
    content: str = Field(..., description="The YAML configuration content")


class ConfigRevision(BaseModel):
    filename: str
    timestamp: datetime
    size: int


class ConfigValidationResult(BaseModel):
    valid: bool
    errors: list[str] = []
    warnings: list[str] = []


class ConfigResponse(BaseModel):
    content: str
    revisions: list[ConfigRevision]


# Config management endpoints
@app.get("/api/config")
async def get_config() -> ConfigResponse:
    """Get current config content and list of revisions."""
    if config is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    config_path = Path(config.config_path)
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Config file not found")

    # Read current config
    with open(config_path) as f:
        content = f.read()

    # Get revisions using config module method
    revision_list = config.get_revisions()
    revisions = [
        ConfigRevision(
            filename=r["filename"],
            timestamp=datetime.strptime(r["timestamp"], "%Y%m%d_%H%M%S"),
            size=r["size"],
        )
        for r in revision_list[:50]  # Limit to 50 most recent
    ]

    return ConfigResponse(content=content, revisions=revisions)


@app.get("/api/config/revision/{filename}")
async def get_config_revision(filename: str) -> dict:
    """Get content of a specific config revision."""
    if config is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    content = config.get_revision_content(filename)
    if content is None:
        raise HTTPException(status_code=404, detail="Revision not found")

    return {"content": content, "filename": Path(filename).name}


@app.post("/api/config/validate")
async def validate_config(config_data: ConfigContent) -> ConfigValidationResult:
    """Validate config without saving."""
    # Use the Config class validation method
    valid, errors = Config.validate_content(config_data.content)

    # For now, we don't have warnings from the Config validation
    # but we can add them later if needed
    warnings = []

    return ConfigValidationResult(valid=valid, errors=errors, warnings=warnings)


@app.post("/api/config")
async def save_config(config_data: ConfigContent) -> dict:
    """Save config after validation and create a backup."""
    global config
    if config is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    success, message = config.save(config_data.content, create_backup=True)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"success": True, "message": message}


class CodeServerInfo(BaseModel):
    enabled: bool
    services: list[dict]
    token_required: bool


@app.get("/api/code-server/info")
async def get_code_server_info() -> CodeServerInfo:
    """Get code server configuration."""
    if config is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    services_with_mount = [
        {
            "name": s.name,
            "port": s.port,
            "mount_folder": s.mount_folder,
            "workspace_path": f"/workspace/{s.name.replace('-', '_')}",
        }
        for s in config.services
        if s.mount_folder
    ]

    return CodeServerInfo(
        enabled=len(services_with_mount) > 0,
        services=services_with_mount,
        token_required=True,
    )


ANALYZER_API_URL = os.environ.get("ANALYZER_API_URL", "http://analyzer-api:8090")


async def analyzer_request(method: str, path: str, *, params: dict | None = None, json=None):
    url = f"{ANALYZER_API_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, params=params, json=json)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Analyzer API unreachable: {e}") from e

    if response.status_code >= 400:
        detail = response.text
        if response.headers.get("content-type", "").startswith("application/json"):
            detail = response.json().get("detail", detail)
        raise HTTPException(status_code=response.status_code, detail=detail)

    return response.json()


@app.get("/api/analyzer/rules", response_model=RuleListResponse)
async def analyzer_list_rules(port: int | None = None):
    params = {"port": port} if port is not None else None
    return await analyzer_request("GET", "/api/rules", params=params)


@app.get("/api/analyzer/rules/{name}", response_model=RuleSourceResponse)
async def analyzer_get_rule(name: str, status: str = "draft"):
    return await analyzer_request("GET", f"/api/rules/{name}", params={"status": status})


@app.put("/api/analyzer/rules/{name}", response_model=MessageResponse)
async def analyzer_save_rule(name: str, body: SaveRuleRequest):
    return await analyzer_request("PUT", f"/api/rules/{name}", json=body.model_dump())


@app.delete("/api/analyzer/rules/{name}", response_model=MessageResponse)
async def analyzer_delete_rule(name: str, status: str = "draft"):
    return await analyzer_request("DELETE", f"/api/rules/{name}", params={"status": status})


@app.post("/api/analyzer/rules/{name}/promote", response_model=MessageResponse)
async def analyzer_promote_rule(name: str):
    return await analyzer_request("POST", f"/api/rules/{name}/promote")


@app.post("/api/analyzer/preview", response_model=PreviewResponse)
async def analyzer_preview(body: PreviewRequest):
    return await analyzer_request("POST", "/api/preview", json=body.model_dump())


@app.get("/api/analyzer/tag-stats", response_model=TagStatsResponse)
async def analyzer_tag_stats(port: int, window_minutes: int = 60):
    return await analyzer_request(
        "GET", "/api/tag-stats", params={"port": port, "window_minutes": window_minutes}
    )


@app.post("/api/analyzer/backfill", response_model=BackfillJobModel)
async def analyzer_create_backfill(body: BackfillRequest):
    return await analyzer_request("POST", "/api/backfill", json=body.model_dump())


@app.get("/api/analyzer/backfill", response_model=BackfillJobModel | None)
async def analyzer_get_backfill():
    return await analyzer_request("GET", "/api/backfill")


async def fetch_tags_for_refs(
    source_type: str, ids: list[int], visible_rules: str | None
) -> dict[int, list[str]]:
    if not ids or visible_rules is None:
        return {}
    rules = [r for r in visible_rules.split(",") if r]
    if not rules:
        return {}
    try:
        result = await analyzer_request(
            "POST",
            "/api/tags/for-refs",
            json={"source_type": source_type, "ids": ids, "rules": rules},
        )
    except HTTPException:
        return {}
    return {int(ref): tags for ref, tags in result.get("tags", {}).items()}


async def fetch_analysis_rows(source_type: str, ref_id: int) -> list[RuleTagItem]:
    try:
        result = await analyzer_request(
            "GET",
            "/api/analysis/for-ref",
            params={"source_type": source_type, "ref_id": ref_id},
        )
    except HTTPException:
        return []
    return [RuleTagItem(**row) for row in result.get("rows", [])]
