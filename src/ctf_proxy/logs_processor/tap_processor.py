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
    HttpResponseCodeStatsRow,
    ProxyStatsDB,
    RowStatus,
    ServiceStatsRow,
)
from ctf_proxy.db.utils import now_timestamp
from ctf_proxy.logs_processor.flags import find_body_flags

DEFAULT_DURATION_MS = 100

logger = logging.getLogger(__name__)


class TapProcessor:
    def __init__(self, db: ProxyStatsDB, config: Config):
        self.db = db
        self.config = config

    def normalize_path(self, path):
        if not path:
            return "/"

        parsed = urlparse(path)
        normalized_path = parsed.path if parsed.path else "/"

        normalized_path = re.sub(r"/\d+(?=/|$)", "/{id}", normalized_path)
        normalized_path = re.sub(
            r"/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(?=/|$)",
            "/{uuid}",
            normalized_path,
            flags=re.IGNORECASE,
        )
        normalized_path = re.sub(
            r"/[a-f0-9]{32,}(?=/|$)", "/{hash}", normalized_path, flags=re.IGNORECASE
        )

        return normalized_path.rstrip("/")

    def extract_query_params(self, path):
        if not path:
            return {}

        parsed = urlparse(path)
        return parse_qs(parsed.query, keep_blank_values=True) if parsed.query else {}

    def get_header_value(self, headers, key):
        for header in headers:
            if header.get("key") == key:
                return header.get("value")
        return None

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

        request_headers = {
            h.get("key").lower(): h.get("value") for h in request.get("headers", []) if h.get("key")
        }
        response_headers = {
            h.get("key").lower(): h.get("value")
            for h in response.get("headers", [])
            if h.get("key")
        }

        method = log_entry.get("method") or request_headers.get(":method")
        path = log_entry.get("path") or request_headers.get(":path")
        status_str = log_entry.get("status") or response_headers.get(":status")
        status = int(status_str) if status_str and str(status_str).isdigit() else -1

        user_agent = request_headers.get("user-agent")
        start_time_str = log_entry.get("start_time")

        start_time = (
            datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
            if start_time_str
            else datetime.now()
        )
        upstream_host = log_entry.get("upstream_host", "")
        port = self.try_get_port_from_upstream_host(upstream_host)

        req_body = self.extract_body(request.get("body"))
        resp_body = self.extract_body(response.get("body"))

        with self.db.connect() as conn:
            tx = conn.cursor()
            request_id = self.db.http_requests.insert(
                tx=tx,
                port=port or 0,
                start_time=int(start_time.timestamp() * 1000),
                path=path or None,
                method=method or None,
                user_agent=user_agent,
                body=req_body,
                tap_id=tap_id,
                batch_id=batch_id,
            )

            response_id = self.db.http_responses.insert(
                tx=tx, request_id=request_id, status=status, body=resp_body
            )

            headers = [
                *(
                    HttpHeaderRow.Insert(request_id=request_id, name=key, value=value)
                    for key, value in request_headers.items()
                ),
                *(
                    HttpHeaderRow.Insert(response_id=response_id, name=key, value=value)
                    for key, value in response_headers.items()
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
                        total_responses=1,
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
                            description=f"New path: '{path}'",
                            http_request_id=request_id,
                            http_response_id=response_id,
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
