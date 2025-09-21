from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ctf_proxy.config import Config
from ctf_proxy.dashboard.models import (
    FlagItem,
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
    ResponseDetail,
    ServiceListItem,
    ServiceListResponse,
)
from ctf_proxy.dashboard.models import (
    ServiceStats as ServiceStatsModel,
)
from ctf_proxy.db import ProxyStatsDB
from ctf_proxy.ui.components.header_stats import HeaderStats
from ctf_proxy.ui.components.path_stats import PathStats
from ctf_proxy.ui.components.query_param_stats import QueryParamStats
from ctf_proxy.ui.components.raw_request_fetcher import fetch_raw_request
from ctf_proxy.ui.components.service_stats import ServiceStats

config: Config | None = None
db: ProxyStatsDB | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os

    try:
        # Use environment variables if set (for reload mode)
        config_path = os.environ.get("CTF_CONFIG_PATH", "../config.yml")
        db_path = os.environ.get("CTF_DB_PATH", "../proxy_stats.db")
        init_app(config_path, db_path)
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


def init_app(config_path: str = "config.yml", db_path: str = "proxy_stats.db") -> None:
    global config, db

    config_file = Path(config_path)
    db_file = Path(db_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    if not db_file.exists():
        raise FileNotFoundError(f"Database file not found: {db_file}")

    config = Config(config_file)
    config.start_watching()
    db = ProxyStatsDB(str(db_file))


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "backend": "ctf-proxy-dashboard",
        "version": "1.0.0"
    }


@app.get("/api/services", response_model=ServiceListResponse)
async def get_services() -> ServiceListResponse:
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    services = []

    for service in config.services:
        stats_obj = ServiceStats(service.port, db)
        current_stats = stats_obj.get_current_stats()

        stats_model = ServiceStatsModel(
            total_requests=current_stats["total_requests"],
            blocked_requests=current_stats["blocked_requests"],
            total_responses=current_stats["total_responses"],
            blocked_responses=current_stats["blocked_responses"],
            error_responses=current_stats["error_responses"],
            success_responses=current_stats["success_responses"],
            redirect_responses=current_stats["redirect_responses"],
            status_counts=current_stats["status_counts"],
            unique_paths=current_stats["unique_paths"],
            alerts_count=current_stats["alerts_count"],
            recent_alerts=current_stats["recent_alerts"],
            flags_written=current_stats["flags_written"],
            flags_retrieved=current_stats["flags_retrieved"],
            flags_blocked=current_stats["flags_blocked"],
            total_flags=current_stats["total_flags"],
            unique_headers=current_stats["unique_headers"],
            unique_header_values=current_stats["unique_header_values"],
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
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    service = config.get_service_by_port(port)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service not found on port {port}")

    stats_obj = ServiceStats(service.port, db)
    current_stats = stats_obj.get_current_stats()

    stats_model = ServiceStatsModel(
        total_requests=current_stats["total_requests"],
        blocked_requests=current_stats["blocked_requests"],
        total_responses=current_stats["total_responses"],
        blocked_responses=current_stats["blocked_responses"],
        error_responses=current_stats["error_responses"],
        success_responses=current_stats["success_responses"],
        redirect_responses=current_stats["redirect_responses"],
        status_counts=current_stats["status_counts"],
        unique_paths=current_stats["unique_paths"],
        alerts_count=current_stats["alerts_count"],
        recent_alerts=current_stats["recent_alerts"],
        flags_written=current_stats["flags_written"],
        flags_retrieved=current_stats["flags_retrieved"],
        flags_blocked=current_stats["flags_blocked"],
        total_flags=current_stats["total_flags"],
        unique_headers=current_stats["unique_headers"],
        unique_header_values=current_stats["unique_header_values"],
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
) -> RequestListResponse:
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    service = config.get_service_by_port(port)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service not found on port {port}")

    requests = []

    with db.connect() as conn:
        cursor = conn.cursor()

        # Build base query with filters
        base_query = """
            FROM http_request req
            LEFT JOIN http_response resp ON req.id = resp.request_id
            WHERE req.port = ?
        """

        params = [port]

        if filter_path:
            base_query += " AND req.path LIKE ?"
            params.append(f"%{filter_path}%")

        if filter_method:
            base_query += " AND req.method = ?"
            params.append(filter_method.upper())

        if filter_status:
            base_query += " AND resp.status = ?"
            params.append(filter_status)

        if filter_blocked is not None:
            base_query += " AND req.is_blocked = ?"
            params.append(1 if filter_blocked else 0)

        # Get total count
        count_query = f"SELECT COUNT(*) {base_query}"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]

        # Get paginated results
        offset = (page - 1) * page_size
        query = f"""
            SELECT
                req.id,
                req.start_time,
                req.method,
                req.path,
                resp.status,
                req.is_blocked,
                req.user_agent,
                (SELECT COUNT(*) FROM flag WHERE flag.http_request_id = req.id) as req_flags_count,
                (SELECT COUNT(*) FROM flag WHERE flag.http_response_id = resp.id) as resp_flags_count,
                (SELECT COUNT(*) FROM http_request_link WHERE to_request_id = req.id) as incoming_links,
                (SELECT COUNT(*) FROM http_request_link WHERE from_request_id = req.id) as outgoing_links
            {base_query}
            ORDER BY req.start_time DESC
            LIMIT ? OFFSET ?
        """

        params.extend([page_size, offset])
        cursor.execute(query, params)
        rows = cursor.fetchall()

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
                incoming_links,
                outgoing_links,
            ) = row

            # Convert nanosecond timestamp to seconds
            timestamp = (
                datetime.fromtimestamp(start_time / 1_000_000_000) if start_time else datetime.now()
            )

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
                    incoming_links=incoming_links or 0,
                    outgoing_links=outgoing_links or 0,
                )
            )

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
        cursor.execute(
            """
            SELECT
                req.method,
                req.path,
                req.body,
                req.user_agent,
                req.start_time,
                req.port,
                req.is_blocked,
                resp.id as response_id,
                resp.status,
                resp.body as response_body
            FROM http_request req
            LEFT JOIN http_response resp ON req.id = resp.request_id
            WHERE req.id = ?
            """,
            (request_id,),
        )

        row = cursor.fetchone()
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
        cursor.execute(
            """
            SELECT name, value
            FROM http_header
            WHERE request_id = ?
            ORDER BY name
            """,
            (request_id,),
        )
        request_headers = [HeaderItem(name=name, value=value) for name, value in cursor.fetchall()]

        # Get request flags
        cursor.execute(
            """
            SELECT id, value, location
            FROM flag
            WHERE http_request_id = ?
            """,
            (request_id,),
        )
        request_flags = [
            FlagItem(id=id, flag=value, reason=location)
            for id, value, location in cursor.fetchall()
        ]

        # Get linked requests
        linked_requests = []

        # Incoming links
        cursor.execute(
            """
            SELECT from_request_id
            FROM http_request_link
            WHERE to_request_id = ?
            """,
            (request_id,),
        )
        incoming_ids = [row[0] for row in cursor.fetchall()]

        # Outgoing links
        cursor.execute(
            """
            SELECT to_request_id
            FROM http_request_link
            WHERE from_request_id = ?
            """,
            (request_id,),
        )
        outgoing_ids = [row[0] for row in cursor.fetchall()]

        # Get info for all linked requests
        all_linked_ids = incoming_ids + outgoing_ids
        if all_linked_ids:
            placeholders = ",".join("?" for _ in all_linked_ids)
            cursor.execute(
                f"""
                SELECT id, method, path, start_time
                FROM http_request
                WHERE id IN ({placeholders})
                """,
                all_linked_ids,
            )

            for req_id, link_method, link_path, link_start_time in cursor.fetchall():
                # Parse path
                if "?" in link_path:
                    link_path_part, _ = link_path.split("?", 1)
                else:
                    link_path_part = link_path

                # Convert timestamp
                link_timestamp = (
                    datetime.fromtimestamp(link_start_time / 1_000_000_000)
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
                    )
                )

        # Convert nanosecond timestamp to seconds
        timestamp = (
            datetime.fromtimestamp(start_time / 1_000_000_000) if start_time else datetime.now()
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
        )

        # Build response detail if exists
        response_detail = None
        if response_id:
            # Get response headers
            cursor.execute(
                """
                SELECT name, value
                FROM http_header
                WHERE response_id = ?
                ORDER BY name
                """,
                (response_id,),
            )
            response_headers = [
                HeaderItem(name=name, value=value) for name, value in cursor.fetchall()
            ]

            # Get response flags
            cursor.execute(
                """
                SELECT id, value, location
                FROM flag
                WHERE http_response_id = ?
                """,
                (response_id,),
            )
            response_flags = [
                FlagItem(id=id, flag=value, reason=location)
                for id, value, location in cursor.fetchall()
            ]

            response_detail = ResponseDetail(
                id=response_id,
                status=status,
                body=response_body,
                headers=response_headers,
                flags=response_flags,
            )

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
