import base64
import logging
import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from psycopg import Cursor

from ctf_proxy.common.config import Config
from ctf_proxy.db.models import (
    AlertRow,
    FlagRow,
    HttpHeaderRow,
    HttpPathStatsRow,
    HttpResponseCodeStatsRow,
    ProxyStatsDB,
    RowStatus,
    ServiceStatsRow,
    SessionLinkRow,
    WebSocketFrameRow,
)
from ctf_proxy.db.stats import (
    FlagTimeStatsRow,
    HttpHeaderTimeStatsRow,
    HttpPathTimeStatsRow,
    HttpQueryParamTimeStatsRow,
    HttpRequestTimeStatsRow,
)
from ctf_proxy.db.utils import convert_datetime_to_timestamp, now_timestamp
from ctf_proxy.logs_ingestion.access_log import AccessLogReader
from ctf_proxy.logs_ingestion.flags import find_body_flags
from ctf_proxy.logs_ingestion.sessions import SessionsStorage
from ctf_proxy.logs_ingestion.taps import TapsFolder
from ctf_proxy.logs_ingestion.utils import try_get_port_from_upstream_host
from ctf_proxy.logs_ingestion.ws import parse_ws_frames

DEFAULT_DURATION_MS = 100

logger = logging.getLogger(__name__)


IGNORED_HEADER_STATS = {
    "content-length",
    ":path",
    "cookie",
    "x-request-id",
}


class HttpTapsFolder(TapsFolder):
    def __init__(self, path: str):
        super().__init__(path)
        self.request_id_to_file: dict[str, str] = {}

    def on_file_loaded(self, filename: str, data: dict):
        request_id = self.extract_request_id_from_tap(filename, data)
        if request_id:
            self.request_id_to_file[request_id] = filename

    def extract_request_id_from_tap(self, filename: str, data: dict) -> str | None:
        try:
            http_trace = data.get("http_buffered_trace", {})
            request = http_trace.get("request", {})
            for header in request.get("headers", []):
                if header.get("key") == "x-request-id":
                    return header.get("value")

            response = http_trace.get("response", {})
            for header in response.get("headers", []):
                if header.get("key") == "x-request-id":
                    return header.get("value")
        except Exception as e:
            logger.error(f"Error extracting request ID from {filename}: {e}")

        logger.error(f"Could not extract request ID from tap file {filename}")
        return None

    def pop_tap_filename_by_request_id(self, request_id: str) -> str | None:
        return self.request_id_to_file.pop(request_id, None)


class HttpProcessor:
    def __init__(self, db: ProxyStatsDB, config: Config, access_log_path: str, taps_dir: str):
        self.db = db
        self.config = config
        self.access_log = AccessLogReader(access_log_path)
        self.taps_folder = HttpTapsFolder(taps_dir)
        self.tap_processor = HttpTapProcessor(db, config)

    def process_new_access_log_entries(self, tx: Cursor, batch_id: str):
        new_entries = self.access_log.read_new_entries(max_entries=1000)
        self.taps_folder.refresh()

        to_archive = {}

        for entry in new_entries:
            log_entry = entry.data
            stream_id = log_entry.get("stream_id")
            if not stream_id:
                # should not happen if access log is well-formed
                logger.warning(f"Access log entry missing stream_id: {log_entry}")
                continue

            tap_filename = self.taps_folder.pop_tap_filename_by_request_id(stream_id)
            if not tap_filename:
                # tap files are written first, if it's missing, just skip it
                logger.warning(f"Tap file not found for stream_id {stream_id}: {log_entry}")
                continue

            tap_data = self.taps_folder.pop_filename(tap_filename)
            if not tap_data:
                logger.warning(f"Tap data not loaded for file {tap_filename}")
                continue

            try:
                self.tap_processor.process_tap(
                    tx=tx,
                    data=tap_data,
                    tap_id=tap_filename,
                    batch_id=batch_id,
                    log_entry=log_entry,
                )
                to_archive[tap_filename] = tap_data
            except Exception as e:
                logger.error(f"Error processing tap file {tap_filename}: {e}")

        if new_entries:
            last_position = new_entries[-1].end_position
            self.access_log.write_last_processed_position(last_position)

        self.taps_folder.cleanup()

        return to_archive

    def check_is_websocket(self, tap_data: dict) -> bool:
        try:
            http_trace = tap_data.get("http_buffered_trace", {})
            request = http_trace.get("request", {})
            request_headers = {
                h.get("key", "").lower(): h.get("value", "")
                for h in request.get("headers", [])
                if h.get("key")
            }
            upgrade_header = request_headers.get("upgrade", "").lower()
            connection_header = request_headers.get("connection", "").lower()
            return upgrade_header == "websocket" and "upgrade" in connection_header
        except Exception:
            return False


class HttpTapPartBody:
    def __init__(self, data: dict):
        self.data = data
        self.bytes: str | None = data.get("as_bytes")


class HttpTapHeaders:
    def __init__(self, data: list[dict]):
        self.data = data
        self.values = {}
        for header in data:
            key = header.get("key") or ""
            normalized_key = key.lower()
            value = header.get("value")
            if normalized_key not in self.values:
                self.values[normalized_key] = []
            self.values[normalized_key].append(value)

    def get(self, key: str, default: str = None) -> str | None:
        values = self.values.get(key.lower())
        if values:
            return values[0]
        return default

    def get_list(self, key: str) -> list[str]:
        return self.values.get(key.lower(), [])


class HttpTapPart:
    def __init__(self, data: dict):
        self.data = data
        self.body = HttpTapPartBody(data.get("body", {}))
        self.headers = HttpTapHeaders(data.get("headers", []))
        self.trailers = HttpTapHeaders(data.get("trailers", []))


class HttpTap:
    def __init__(self, data: dict):
        self.data = data
        buffered_trace = data.get("http_buffered_trace", {})
        self.request = HttpTapPart(buffered_trace.get("request", {}))
        self.response = HttpTapPart(buffered_trace.get("response", {}))


class HttpTapProcessor:
    def __init__(self, db: ProxyStatsDB, config: Config):
        self.db = db
        self.config = config
        self.sessions = SessionsStorage(self.config)

    def process_tap(
        self, tx: Cursor, data: dict, tap_id: str, batch_id: str, log_entry: dict
    ):
        tap = HttpTap(data)
        # http_trace = data.get("http_buffered_trace", {})
        # request = http_trace.get("request", {})
        # response = http_trace.get("response", {})

        # request_headers = [
        #     (h.get("key").lower(), h.get("value"))
        #     for h in request.get("headers", [])
        #     if h.get("key")
        # ]
        # request_headers_dict = dict(request_headers)
        # request_trailers = {
        #     h.get("key").lower(): h.get("value")
        #     for h in request.get("trailers", [])
        #     if h.get("key")
        # }
        # response_headers = [
        #     (h.get("key").lower(), h.get("value"))
        #     for h in response.get("headers", [])
        #     if h.get("key")
        # ]
        # response_headers_dict = dict(response_headers)

        is_blocked = tap.request.trailers.get("x-blocked") == "1"

        upgrade_header = tap.request.headers.get("upgrade", "").lower()
        connection_header = tap.request.headers.get("connection", "").lower()
        is_websocket = upgrade_header == "websocket" and "upgrade" in connection_header

        method = log_entry.get("method") or tap.request.headers.get(":method")
        full_path = log_entry.get("path") or tap.request.headers.get(":path") or ""
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

        status_str = log_entry.get("status") or tap.response.headers.get(":status")
        status = int(status_str) if status_str and str(status_str).isdigit() else -1

        user_agent = tap.request.headers.get("user-agent")
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
        port = try_get_port_from_upstream_host(upstream_host)

        service_config = self.config.get_service_by_port(port) if port else None

        req_body = self.decode_body(tap.request.body.bytes)
        resp_body = self.decode_body(tap.response.body.bytes)

        request_id = self.db.http_requests.insert(
            tx=tx,
            port=port or 0,
            start_time=convert_datetime_to_timestamp(start_time),
            path=full_path,
            method=method or "",
            user_agent=user_agent,
            body=req_body,
            is_blocked=is_blocked,
            is_websocket=is_websocket,
            tap_id=tap_id,
            batch_id=batch_id,
        )

        response_id = self.db.http_responses.insert(
            tx=tx, request_id=request_id, status=status, body=resp_body
        )

        headers = [
            *(
                HttpHeaderRow.Insert(request_id=request_id, name=key, value=value)
                for key, values in tap.request.headers.values.items()
                for value in values
            ),
            *(
                HttpHeaderRow.Insert(response_id=response_id, name=key, value=value)
                for key, values in tap.response.headers.values.items()
                for value in values
            ),
        ]
        if headers:
            self.db.http_headers.insert_many(tx=tx, headers=headers)

        if not is_websocket:
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
        else:
            flags_written = []
            flags_retrieved = []
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
            if not service_config or not any(
                re.fullmatch(ignored.path, path) and method == ignored.method
                for ignored in service_config.ignore_path_stats
            ):
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
            for key, values in tap.request.headers.values.items():
                if key in IGNORED_HEADER_STATS:
                    continue
                reg = (
                    re.compile(service_config.ignore_header_stats[key])
                    if service_config and key in service_config.ignore_header_stats
                    else None
                )
                for value in values:
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

            self.db.http_request_time_stats.increment(
                tx,
                HttpRequestTimeStatsRow.Increment(
                    port=port,
                    time=start_minute_ts,
                    count=1,
                    blocked_count=1 if is_blocked else 0,
                ),
            )

            if flags_written or flags_retrieved:
                self.db.flag_time_stats.increment(
                    tx,
                    FlagTimeStatsRow.Increment(
                        port=port,
                        time=start_minute_ts,
                        write_count=len(flags_written),
                        read_count=len(flags_retrieved),
                    ),
                )

            sessions = self.sessions.add_request(
                port=port,
                request_id=request_id,
                start_time=start_time_ts,
                request_headers=tap.request.headers.values,
                response_headers=tap.response.headers.values,
            )
            for session in sessions:
                self.db.session_links.insert(
                    tx,
                    SessionLinkRow.Insert(
                        port=port,
                        session_key=session,
                        http_request_id=request_id,
                    ),
                )

        if is_websocket:
            self.process_websocket(tx, tap, log_entry, request_id)

        return request_id

    def process_websocket(
        self, tx: Cursor, tap: HttpTap, log_entry: dict, http_request_id: int
    ):
        connection_id = self.db.websocket_connections.insert(
            tx=tx,
            http_request_id=http_request_id,
        )

        request_frames = parse_ws_frames(
            tap.request.body.bytes,
            is_client=True,
            extensions_header=", ".join(tap.request.headers.get_list("sec-websocket-extensions")),
            max_size=None,  # todo what to pass
        )

        response_frames = parse_ws_frames(
            tap.response.body.bytes,
            is_client=False,
            extensions_header=", ".join(tap.response.headers.get_list("sec-websocket-extensions")),
            max_size=None,  # todo what to pass
        )

        frames_rows = [
            *(
                WebSocketFrameRow.Insert(
                    connection_id=connection_id,
                    order=i,
                    opcode=opcode.name,
                    payload=payload,
                    payload_text=payload.decode("utf-8", errors="ignore"),
                    payload_size=len(payload),
                    is_client=True,
                )
                for i, (fin, opcode, payload) in enumerate(request_frames)
            ),
            *(
                WebSocketFrameRow.Insert(
                    connection_id=connection_id,
                    order=i,
                    opcode=opcode.name,
                    payload=payload,
                    payload_text=payload.decode("utf-8", errors="ignore"),
                    payload_size=len(payload),
                    is_client=False,
                )
                for i, (fin, opcode, payload) in enumerate(response_frames)
            ),
        ]

        if frames_rows:
            self.db.websocket_frames.insert_many(
                tx=tx,
                frames=frames_rows,
            )

    def decode_body(self, body_data: str | None) -> str | None:
        if body_data is None:
            return None

        return base64.b64decode(body_data).decode("utf-8", errors="ignore")
