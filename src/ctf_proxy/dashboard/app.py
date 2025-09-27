import csv
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime
from io import StringIO
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from ctf_proxy.config import Config
from ctf_proxy.config.config import verify_token
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
    ServiceListItem,
    ServiceListResponse,
    TCPConnectionDetail,
    TCPConnectionItem,
    TCPConnectionListResponse,
    TCPConnectionStatsItem,
    TCPConnectionStatsResponse,
    TCPEventItem,
    TCPStats,
)
from ctf_proxy.dashboard.models import (
    ServiceStats as ServiceStatsModel,
)
from ctf_proxy.db import ProxyStatsDB
from ctf_proxy.db.utils import convert_timestamp_to_datetime
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
        # Use environment variables if set (for Gunicorn/Docker mode)
        config_path = os.environ.get(
            "CONFIG_PATH", os.environ.get("CTF_CONFIG_PATH", "../config.yml")
        )
        db_path = os.environ.get("DB_PATH", os.environ.get("CTF_DB_PATH", "../proxy_stats.db"))
        init_app(config_path, db_path)
    except FileNotFoundError as e:
        print(f"Warning: {e}")
        print("Server will start but endpoints will return errors until properly initialized")
    yield
    if config:
        config.stop_watching()


app = FastAPI(title="CTF Proxy Dashboard API", version="1.0.0", lifespan=lifespan)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # All /api routes require authentication
        if request.url.path.startswith("/api"):
            auth_header = request.headers.get("Authorization")
            if not auth_header:
                return Response(
                    content='{"detail":"Missing Authorization header"}',
                    status_code=401,
                    media_type="application/json",
                )

            if not auth_header.startswith("Bearer "):
                return Response(
                    content='{"detail":"Invalid authorization header format"}',
                    status_code=401,
                    media_type="application/json",
                )

            token = auth_header[7:]  # Remove "Bearer " prefix

            if config is None:
                return Response(
                    content='{"detail":"Server not properly initialized"}',
                    status_code=500,
                    media_type="application/json",
                )

            expected_token_hash = getattr(config, "api_token_hash", None)
            if not expected_token_hash:
                return Response(
                    content='{"detail":"API token not configured"}',
                    status_code=500,
                    media_type="application/json",
                )

            if not verify_token(token, expected_token_hash):
                return Response(
                    content='{"detail":"Invalid API token"}',
                    status_code=401,
                    media_type="application/json",
                )

        return await call_next(request)


app.add_middleware(AuthMiddleware)
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
    except sqlite3.Error as e:
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
    except sqlite3.Error as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def get_all_services_stats_optimized(ports: list[int], db_instance) -> dict:
    """Fetch stats for all services in optimized batch queries."""
    import logging
    from datetime import datetime

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    with db_instance.connect() as conn:
        cursor = conn.cursor()

        # Build placeholders for IN clause
        placeholders = ",".join("?" * len(ports))

        five_minutes_ago = int(time.time() * 1000) - (5 * 60 * 1000)

        # 1. Get service stats for all ports at once
        start = time.time()
        cursor.execute(
            f"""SELECT port, total_requests, total_blocked_requests, total_responses, total_blocked_responses,
                      total_flags_written, total_flags_retrieved, total_flags_blocked
               FROM service_stats WHERE port IN ({placeholders})""",
            ports,
        )
        service_stats = {row[0]: row[1:] for row in cursor.fetchall()}
        logger.info(f"Query 1 (service_stats): {time.time() - start:.3f}s")

        # 2. Get response code stats for all ports
        start = time.time()
        cursor.execute(
            f"""SELECT port, status_code, count
               FROM http_response_code_stats
               WHERE port IN ({placeholders})
               ORDER BY port, count DESC""",
            ports,
        )
        response_codes = {}
        for port, status_code, count in cursor.fetchall():
            if port not in response_codes:
                response_codes[port] = {}
            response_codes[port][status_code] = count
        logger.info(f"Query 2 (response_codes): {time.time() - start:.3f}s")

        # 3. Skip unique paths count - too slow with large datasets
        unique_paths = {}

        # 4. Get alerts count for all ports
        start = time.time()
        cursor.execute(
            f"""SELECT port, COUNT(*)
               FROM alert
               WHERE port IN ({placeholders})
               GROUP BY port""",
            ports,
        )
        alerts_count = dict(cursor.fetchall())
        logger.info(f"Query 4 (alerts_count): {time.time() - start:.3f}s")

        # 5. Get recent alerts for all ports - skip for now, too slow
        recent_alerts = {}

        # 6. Skip header stats - too slow with large datasets
        header_stats = {}

        # 7. Skip TCP stats for now - tcp_stats table is not populated
        tcp_stats = {}

        # 8. Get request count delta for last 5 minutes using stats table
        start = time.time()
        five_minutes_ago_datetime = datetime.fromtimestamp(five_minutes_ago / 1000)
        cursor.execute(
            f"""SELECT port, SUM(count) as recent_count
               FROM http_request_time_stats
               WHERE port IN ({placeholders})
                 AND time >= ?
               GROUP BY port""",
            ports + [five_minutes_ago_datetime],
        )
        request_deltas = dict(cursor.fetchall())
        logger.info(f"Query 8 (request_deltas): {time.time() - start:.3f}s")

        # 9. Get blocked request count delta for last 5 minutes using stats table
        start = time.time()
        cursor.execute(
            f"""SELECT port, SUM(blocked_count) as recent_blocked_count
               FROM http_request_time_stats
               WHERE port IN ({placeholders})
                 AND time >= ?
               GROUP BY port""",
            ports + [five_minutes_ago_datetime],
        )
        blocked_request_deltas = dict(cursor.fetchall())
        logger.info(f"Query 9 (blocked_request_deltas): {time.time() - start:.3f}s")

        # 10. Get flag deltas for last 5 minutes
        start = time.time()
        cursor.execute(
            f"""SELECT port,
                       SUM(write_count) as flags_written_delta,
                       SUM(read_count) as flags_retrieved_delta
               FROM flag_time_stats
               WHERE port IN ({placeholders})
                 AND time >= ?
               GROUP BY port""",
            ports + [five_minutes_ago_datetime],
        )
        flag_deltas = {}
        for row in cursor.fetchall():
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
                "alerts_count": alerts_count.get(port, 0),
                "recent_alerts": recent_alerts.get(port, []),
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
            requests_delta=stats.get("requests_delta", 0),
            blocked_requests_delta=stats.get("blocked_requests_delta", 0),
            error_responses=stats.get("error_responses", 0),
            success_responses=stats.get("success_responses", 0),
            redirect_responses=stats.get("redirect_responses", 0),
            status_counts=stats.get("status_counts", {}),
            unique_paths=stats.get("unique_paths", 0),
            alerts_count=stats.get("alerts_count", 0),
            recent_alerts=stats.get("recent_alerts", []),
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
    from datetime import datetime

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
    five_minutes_ago_datetime = datetime.fromtimestamp(five_minutes_ago / 1000)

    with db.connect() as conn:
        cursor = conn.cursor()

        # Use stats table instead of raw http_request table
        start = time.time()
        cursor.execute(
            """SELECT SUM(count) FROM http_request_time_stats
               WHERE port = ? AND time >= ?""",
            (service.port, five_minutes_ago_datetime),
        )
        requests_delta = cursor.fetchone()[0] or 0
        logger.info(f"requests_delta query took {time.time() - start:.3f}s")

        start = time.time()
        cursor.execute(
            """SELECT SUM(blocked_count) FROM http_request_time_stats
               WHERE port = ? AND time >= ?""",
            (service.port, five_minutes_ago_datetime),
        )
        blocked_requests_delta = cursor.fetchone()[0] or 0
        logger.info(f"blocked_requests_delta query took {time.time() - start:.3f}s")

        start = time.time()
        cursor.execute(
            """SELECT SUM(write_count), SUM(read_count)
               FROM flag_time_stats
               WHERE port = ? AND time >= ?""",
            (service.port, five_minutes_ago_datetime),
        )
        flag_delta_result = cursor.fetchone()
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
        requests_delta=requests_delta,
        blocked_requests_delta=blocked_requests_delta,
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

        # First get the IDs of the requests we'll display
        id_query = f"""
            SELECT req.id
            {base_query}
            ORDER BY req.start_time DESC
            LIMIT ? OFFSET ?
        """

        id_params = params.copy()
        id_params.extend([page_size, offset])
        cursor.execute(id_query, id_params)
        request_ids = [row[0] for row in cursor.fetchall()]

        if not request_ids:
            return RequestListResponse(
                requests=[],
                total=total_count,
                service_name=service.name,
                service_port=port,
                page=page,
                page_size=page_size,
                total_pages=(total_count + page_size - 1) // page_size if total_count > 0 else 0,
            )

        # Now get all data for these requests with optimized joins
        query = """
            WITH request_data AS (
                SELECT
                    req.id,
                    req.start_time,
                    req.method,
                    req.path,
                    resp.status,
                    resp.id as response_id,
                    req.is_blocked,
                    req.user_agent
                FROM http_request req
                LEFT JOIN http_response resp ON req.id = resp.request_id
                WHERE req.id IN ({})
            ),
            flag_counts AS (
                SELECT
                    http_request_id,
                    COUNT(*) as req_count
                FROM flag
                WHERE http_request_id IN ({})
                GROUP BY http_request_id
            ),
            resp_flag_counts AS (
                SELECT
                    http_response_id,
                    COUNT(*) as resp_count
                FROM flag
                WHERE http_response_id IN (
                    SELECT response_id FROM request_data WHERE response_id IS NOT NULL
                )
                GROUP BY http_response_id
            ),
            session_counts AS (
                SELECT
                    sl.http_request_id,
                    SUM(s.count) as total_session_requests
                FROM session_link sl
                JOIN session s ON sl.session_id = s.id
                WHERE sl.http_request_id IN ({})
                GROUP BY sl.http_request_id
            )
            SELECT
                rd.id,
                rd.start_time,
                rd.method,
                rd.path,
                rd.status,
                rd.is_blocked,
                rd.user_agent,
                COALESCE(fc.req_count, 0) as req_flags_count,
                COALESCE(rfc.resp_count, 0) as resp_flags_count,
                COALESCE(sc.total_session_requests, 0) as total_session_requests
            FROM request_data rd
            LEFT JOIN flag_counts fc ON rd.id = fc.http_request_id
            LEFT JOIN resp_flag_counts rfc ON rd.response_id = rfc.http_response_id
            LEFT JOIN session_counts sc ON rd.id = sc.http_request_id
            ORDER BY rd.start_time DESC
        """.format(
            ",".join(["?"] * len(request_ids)),
            ",".join(["?"] * len(request_ids)),
            ",".join(["?"] * len(request_ids)),
        )

        cursor.execute(query, request_ids * 2 + request_ids)
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
            FlagItem(id=id, flag=value, location=location)
            for id, value, location in cursor.fetchall()
        ]

        # Get linked requests
        linked_requests = []

        # Get all requests in the same session with session key
        cursor.execute(
            """
            SELECT DISTINCT sl2.http_request_id,
                   CASE
                     WHEN sl2.http_request_id < ? THEN 'incoming'
                     WHEN sl2.http_request_id > ? THEN 'outgoing'
                   END as direction,
                   s.key as session_key
            FROM session_link sl1
            JOIN session_link sl2 ON sl1.session_id = sl2.session_id
            JOIN session s ON s.id = sl1.session_id
            WHERE sl1.http_request_id = ?
              AND sl2.http_request_id != ?
            ORDER BY sl2.http_request_id
            """,
            (request_id, request_id, request_id, request_id),
        )

        linked_info = cursor.fetchall()
        incoming_ids = [row[0] for row in linked_info if row[1] == "incoming"]
        outgoing_ids = [row[0] for row in linked_info if row[1] == "outgoing"]
        session_key = linked_info[0][2] if linked_info else None

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
                FlagItem(id=id, flag=value, location=location)
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


def get_tcp_stats_for_port(port: int) -> TCPStats | None:
    if db is None:
        return None

    with db.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                total_connections,
                total_bytes_in,
                total_bytes_out,
                avg_duration_ms,
                total_flags_found
            FROM tcp_stats
            WHERE port = ?
        """,
            (port,),
        )

        row = cursor.fetchone()
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
) -> TCPConnectionListResponse:
    if config is None or db is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")

    service = config.get_service_by_port(port)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service not found on port {port}")

    if service.type.value != "tcp":
        raise HTTPException(status_code=400, detail=f"Service on port {port} is not a TCP service")

    offset = (page - 1) * page_size

    with db.connect() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) FROM tcp_connection WHERE port = ?
        """,
            (port,),
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            """
            WITH tcp_ids AS (
                SELECT id FROM tcp_connection
                WHERE port = ?
                ORDER BY start_time DESC
                LIMIT ? OFFSET ?
            )
            SELECT
                tc.id, tc.connection_id, tc.start_time, tc.duration_ms,
                tc.bytes_in, tc.bytes_out,
                COALESCE(f_in.count, 0) as flags_in,
                COALESCE(f_out.count, 0) as flags_out,
                tc.is_blocked
            FROM tcp_connection tc
            LEFT JOIN (
                SELECT tcp_connection_id, COUNT(*) as count
                FROM flag
                WHERE location = 'read' AND tcp_connection_id IN (SELECT id FROM tcp_ids)
                GROUP BY tcp_connection_id
            ) f_in ON tc.id = f_in.tcp_connection_id
            LEFT JOIN (
                SELECT tcp_connection_id, COUNT(*) as count
                FROM flag
                WHERE location = 'write' AND tcp_connection_id IN (SELECT id FROM tcp_ids)
                GROUP BY tcp_connection_id
            ) f_out ON tc.id = f_out.tcp_connection_id
            WHERE tc.id IN (SELECT id FROM tcp_ids)
            ORDER BY tc.start_time DESC
        """,
            (port, page_size, offset),
        )

        connections = []
        for row in cursor.fetchall():
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

        cursor.execute(
            """
            SELECT
                tc.id, tc.connection_id, tc.port, tc.start_time, tc.duration_ms,
                tc.bytes_in, tc.bytes_out, tc.is_blocked
            FROM tcp_connection tc
            WHERE tc.id = ?
        """,
            (connection_id,),
        )

        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"TCP connection not found: {connection_id}"
            )

        cursor.execute(
            """
            SELECT
                te.id, te.timestamp, te.event_type, te.data_size, te.data,
                te.truncated, te.end_stream
            FROM tcp_event te
            WHERE te.connection_id = ?
            ORDER BY te.timestamp
        """,
            (connection_id,),
        )

        events = []
        for event_row in cursor.fetchall():
            event_id = event_row[0]

            cursor.execute(
                """
                SELECT value FROM flag WHERE tcp_event_id = ?
            """,
                (event_id,),
            )
            flags = [f[0] for f in cursor.fetchall()]

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

        cursor.execute(
            """
            SELECT COUNT(*) FROM flag WHERE tcp_connection_id = ?
        """,
            (connection_id,),
        )
        total_flags = cursor.fetchone()[0]

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
        cursor.execute(
            """
            SELECT read_min, read_max, write_min, write_max, time, SUM(count) as count
            FROM tcp_connection_time_stats
            WHERE port = ? AND time >= ?
            GROUP BY read_min, read_max, write_min, write_max, time
            ORDER BY read_min, write_min, time
        """,
            (port, start_timestamp),
        )

        # Group by byte ranges and create time series
        stats_map = {}
        for row in cursor.fetchall():
            read_min, read_max, write_min, write_max, time, count = row
            key = (read_min, read_max, write_min, write_max)

            if key not in stats_map:
                stats_map[key] = {"total_count": 0, "blocked_count": 0, "time_points": []}

            stats_map[key]["total_count"] += count
            stats_map[key]["time_points"].append({"timestamp": time, "count": count})

        # Get blocked counts for each byte range pattern
        cursor.execute(
            """
            SELECT bytes_in, bytes_out, COUNT(*) as blocked_count
            FROM tcp_connection
            WHERE port = ? AND start_time >= ? AND is_blocked = 1
            GROUP BY bytes_in, bytes_out
        """,
            (port, start_timestamp),
        )

        # Map blocked counts to the corresponding ranges
        for row in cursor.fetchall():
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


@app.get("/api/flags/recent", response_model=FlagTimeStatsResponse)
def get_recent_flag_stats() -> FlagTimeStatsResponse:
    """Get flag statistics for the last 5 minutes."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    five_minutes_ago = int(time.time() * 1000) - (5 * 60 * 1000)

    with db.connect() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT port, time, write_count, read_count
            FROM flag_time_stats
            WHERE time >= ?
            ORDER BY time DESC
            """,
            (five_minutes_ago,),
        )

        stats = []
        for row in cursor.fetchall():
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

        cursor.execute(
            """
            SELECT port, time, write_count, read_count
            FROM flag_time_stats
            WHERE port = ? AND time >= ?
            ORDER BY time ASC
            """,
            (port, start_time),
        )

        stats = []
        for row in cursor.fetchall():
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

        cursor.execute(
            """
            SELECT port, time, count, blocked_count
            FROM http_request_time_stats
            WHERE port = ? AND time >= ?
            ORDER BY time ASC
            """,
            (port, start_time),
        )

        stats = []
        for row in cursor.fetchall():
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

        cursor.execute(
            """
            SELECT port, time, count, blocked_count
            FROM http_request_time_stats
            WHERE time >= ?
            ORDER BY port, time ASC
            """,
            (start_time,),
        )

        stats = []
        for row in cursor.fetchall():
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

        cursor.execute(
            """
            SELECT port, time, write_count, read_count
            FROM flag_time_stats
            WHERE time >= ?
            ORDER BY port, time ASC
            """,
            (start_time,),
        )

        stats = []
        for row in cursor.fetchall():
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
