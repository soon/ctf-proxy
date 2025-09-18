import base64
import json
import logging
import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from ctf_proxy.config.config import Config
from ctf_proxy.db.models import (
    AlertRow,
    FlagRow,
    HttpHeaderRow,
    HttpPathStatsRow,
    HttpRequestLinkRow,
    HttpResponseCodeStatsRow,
    ProxyStatsDB,
    RowStatus,
    ServiceStatsRow,
)
from ctf_proxy.db.stats import (
    HttpHeaderTimeStatsRow,
    HttpPathTimeStatsRow,
    HttpQueryParamTimeStatsRow,
)
from ctf_proxy.db.utils import convert_datetime_to_timestamp, now_timestamp
from ctf_proxy.logs_processor.flags import find_body_flags
from ctf_proxy.logs_processor.sessions import SessionsStorage

DEFAULT_DURATION_MS = 100

logger = logging.getLogger(__name__)


IGNORED_HEADER_STATS = {
    "content-length",
    ":path",
    "cookie",
    "x-request-id",
}


class TapProcessor:
    def __init__(self, db: ProxyStatsDB, config: Config):
        self.db = db
        self.config = config
        self.sessions = SessionsStorage(self.config)

    def process_tap_file(
        self, tap_file_path: str, tap_id: str, batch_id: str, log_entry: dict | None = None
    ):
        if not log_entry:
            log_entry = {}

        with open(tap_file_path) as f:
            data = json.load(f)

        http_trace = data.get("http_buffered_trace", {})
        request = http_trace.get("request", {})
        response = http_trace.get("response", {})

        request_headers = [
            (h.get("key").lower(), h.get("value"))
            for h in request.get("headers", [])
            if h.get("key")
        ]
        request_headers_dict = dict(request_headers)
        request_trailers = {
            h.get("key").lower(): h.get("value")
            for h in request.get("trailers", [])
            if h.get("key")
        }
        response_headers = [
            (h.get("key").lower(), h.get("value"))
            for h in response.get("headers", [])
            if h.get("key")
        ]
        response_headers_dict = dict(response_headers)

        is_blocked = request_trailers.get("x-blocked") == "1"

        method = log_entry.get("method") or request_headers_dict.get(":method")
        full_path = log_entry.get("path") or request_headers_dict.get(":path") or ""
        try:
            parsed_url = urlparse(full_path)
            path = parsed_url.path
            query = parsed_url.query
        except Exception:
            path = full_path
            query = ""

        try:
            query_params = parse_qs(query, keep_blank_values=True) if query else {}
        except Exception:
            query_params = {}

        status_str = log_entry.get("status") or response_headers_dict.get(":status")
        status = int(status_str) if status_str and str(status_str).isdigit() else -1

        user_agent = request_headers_dict.get("user-agent")
        start_time_str = log_entry.get("start_time")

        start_time = (
            datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
            if start_time_str
            else datetime.now()
        )
        start_time_ts = convert_datetime_to_timestamp(start_time)
        start_minute = start_time.replace(second=0, microsecond=0)
        start_minute_ts = convert_datetime_to_timestamp(start_minute)

        upstream_host = log_entry.get("upstream_host", "")
        port = self.try_get_port_from_upstream_host(upstream_host)

        service_config = self.config.get_service_by_port(port) if port else None

        req_body = self.extract_body(request.get("body"))
        resp_body = self.extract_body(response.get("body"))

        with self.db.connect() as conn:
            tx = conn.cursor()
            request_id = self.db.http_requests.insert(
                tx=tx,
                port=port or 0,
                start_time=convert_datetime_to_timestamp(start_time),
                path=full_path,
                method=method or "",
                user_agent=user_agent,
                body=req_body,
                is_blocked=is_blocked,
                tap_id=tap_id,
                batch_id=batch_id,
            )

            response_id = self.db.http_responses.insert(
                tx=tx, request_id=request_id, status=status, body=resp_body
            )

            headers = [
                *(
                    HttpHeaderRow.Insert(request_id=request_id, name=key, value=value)
                    for key, value in request_headers
                ),
                *(
                    HttpHeaderRow.Insert(response_id=response_id, name=key, value=value)
                    for key, value in response_headers
                ),
            ]
            if headers:
                self.db.http_headers.insert_many(tx=tx, headers=headers)

            flags_written = [
                FlagRow.Insert(
                    value=flag,
                    http_request_id=request_id,
                    location="body",
                    offset=offset,
                )
                for offset, flag in find_body_flags(req_body or "", self.config.flag_format)
            ]
            flags_retrieved = [
                FlagRow.Insert(
                    value=flag,
                    http_response_id=response_id,
                    location="body",
                    offset=offset,
                )
                for offset, flag in find_body_flags(resp_body or "", self.config.flag_format)
            ]
            flags = [
                *flags_written,
                *flags_retrieved,
            ]
            if flags:
                self.db.flags.insert_many(tx=tx, flags=flags)
            if port:
                self.db.service_stats.increment(
                    tx,
                    ServiceStatsRow.Increment(
                        port=port,
                        total_requests=1,
                        total_responses=1 if not is_blocked else 0,
                        total_blocked_requests=1 if is_blocked else 0,
                        total_flags_written=len(flags_written),
                        total_flags_retrieved=len(flags_retrieved),
                    ),
                )
                self.db.http_response_code_stats.increment(
                    tx,
                    HttpResponseCodeStatsRow.Increment(
                        port=port,
                        status_code=status,
                        count=1,
                    ),
                )
                path_stats_result = self.db.http_path_stats.increment(
                    tx,
                    HttpPathStatsRow.Increment(
                        port=port,
                        path=path,
                        count=1,
                    ),
                )
                if path_stats_result == RowStatus.NEW:
                    self.db.alerts.insert(
                        tx,
                        AlertRow.Insert(
                            port=port,
                            created=now_timestamp(),
                            description=f"New path: '{full_path}'",
                            http_request_id=request_id,
                            http_response_id=response_id,
                        ),
                    )
                if not service_config or not any(
                    re.fullmatch(ignored.path, path) and method == ignored.method
                    for ignored in service_config.ignore_path_stats
                ):
                    self.db.http_path_time_stats.increment(
                        tx,
                        HttpPathTimeStatsRow.Increment(
                            port=port,
                            method=method,
                            path=path,
                            time=start_minute_ts,
                            count=1,
                        ),
                    )
                for param, values in query_params.items():
                    reg = (
                        re.compile(service_config.ignore_query_param_stats[param])
                        if service_config and param in service_config.ignore_query_param_stats
                        else None
                    )
                    for value in values:
                        if reg and reg.fullmatch(value):
                            continue
                        self.db.http_query_param_time_stats.increment(
                            tx,
                            HttpQueryParamTimeStatsRow.Increment(
                                port=port,
                                param=param,
                                value=value,
                                time=start_minute_ts,
                                count=1,
                            ),
                        )
                for key, value in request_headers:
                    if key in IGNORED_HEADER_STATS:
                        continue
                    reg = (
                        re.compile(service_config.ignore_header_stats[key])
                        if service_config and key in service_config.ignore_header_stats
                        else None
                    )
                    if reg and reg.fullmatch(value):
                        continue
                    self.db.http_header_time_stats.increment(
                        tx,
                        HttpHeaderTimeStatsRow.Increment(
                            port=port,
                            name=key,
                            value=value,
                            time=start_minute_ts,
                            count=1,
                        ),
                    )
                self.sessions.add_request(
                    port=port,
                    request_id=request_id,
                    start_time=start_time_ts,
                    request_headers=request_headers,
                    response_headers=response_headers,
                )
                for link in self.sessions.get_links(port, request_id):
                    self.db.http_request_links.insert(
                        tx,
                        HttpRequestLinkRow.Insert(
                            from_request_id=link.from_request_id,
                            to_request_id=link.to_request_id,
                        ),
                    )

        logger.debug(f"Processed tap file {tap_file_path} with log data (request_id: {request_id})")

    def try_get_port_from_upstream_host(self, upstream_host: str) -> int | None:
        if not upstream_host:
            return None

        loc = upstream_host.rfind(":")
        if loc == -1:
            return None
        port_str = upstream_host[loc + 1 :]

        try:
            # todo - can there be ipv6 without port?
            return int(port_str)
        except ValueError:
            return None

    def extract_body(self, body_data):
        if not body_data:
            return None

        return base64.b64decode(body_data.get("as_bytes")).decode("utf-8", errors="ignore")
