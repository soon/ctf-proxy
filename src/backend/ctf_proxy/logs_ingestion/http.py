import base64
import json
import logging
import os
import re
from datetime import datetime
from time import perf_counter
from urllib.parse import parse_qs, urlparse

from psycopg import Cursor

from ctf_proxy.common.config import Config
from ctf_proxy.db.connection import nul_safe
from ctf_proxy.db.models import (
    AlertRow,
    FlagRow,
    HttpRequestRow,
    HttpResponseRow,
    ProxyStatsDB,
    SessionLinkRow,
    WebSocketConnectionRow,
    WebSocketFrameRow,
)
from ctf_proxy.db.refs import Ref
from ctf_proxy.db.utils import convert_datetime_to_timestamp, now_timestamp
from ctf_proxy.logs_ingestion.access_log import AccessLogReader
from ctf_proxy.logs_ingestion.batch_stats import BatchStats
from ctf_proxy.logs_ingestion.batch_writer import (
    Batch,
    flush_objects,
    flush_with_isolation_fallback,
)
from ctf_proxy.logs_ingestion.flags import find_body_flags
from ctf_proxy.logs_ingestion.sessions import SessionsStorage
from ctf_proxy.logs_ingestion.taps import TapsFolder
from ctf_proxy.logs_ingestion.utils import try_get_port_from_upstream_host
from ctf_proxy.logs_ingestion.ws import parse_ws_frames

DEFAULT_DURATION_MS = 100

# TEMP diagnostic: set PER_TABLE_TX=1 to flush each table in its own transaction and
# log per-table time. Off by default (uses the normal single-transaction flush).
PER_TABLE_TX = os.environ.get("PER_TABLE_TX") == "1"

logger = logging.getLogger(__name__)


IGNORED_HEADER_STATS = {
    "content-length",
    ":path",
    "cookie",
    "x-request-id",
}


def serialize_headers(headers: "HttpTapHeaders") -> str:
    return json.dumps(
        [[name, value] for name, values in headers.values.items() for value in values],
        separators=(",", ":"),
    )

class PathStatsAggregator:
    def __init__(self):
        self.counts: dict[tuple, int] = {}
        self.first: dict[tuple, tuple] = {}

    def record(self, port: int, path: str, full_path: str, request_ref: Ref, response_ref: Ref):
        key = (port, path)
        self.counts[key] = self.counts.get(key, 0) + 1
        if key not in self.first:
            self.first[key] = (full_path, request_ref, response_ref)

    def flush(self, tx: Cursor, isolate: bool = False) -> None:
        if not self.counts:
            return

        items = list(self.counts.items())
        new_paths: set[tuple] = set()
        for start in range(0, len(items), 1000):
            chunk = items[start : start + 1000]
            values = ", ".join(["(%s, %s, %s)"] * len(chunk))
            params: list = []
            for (port, path), count in chunk:
                params.extend((port, nul_safe(path), count))
            tx.execute(
                f"INSERT INTO http_path_stats (port, path, count) VALUES {values} "
                "ON CONFLICT (port, path) DO UPDATE SET count = http_path_stats.count + EXCLUDED.count "
                "RETURNING port, path, (xmax = 0) AS inserted",
                params,
            )
            new_paths.update((row[0], row[1]) for row in tx.fetchall() if row[2])

        created = now_timestamp()
        alerts = []
        for key in new_paths:
            full_path, request_ref, response_ref = self.first[key]
            if not request_ref.resolved:
                continue
            port, _ = key
            alerts.append(
                AlertRow.Insert(
                    port=port,
                    created=created,
                    description=f"New path: '{full_path}'",
                    http_request_id=request_ref.value,
                    http_response_id=response_ref.value if response_ref.resolved else None,
                )
            )
        if alerts:
            flush_objects(tx, alerts, isolate=isolate)


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
        t_start = perf_counter()
        new_entries = self.access_log.read_new_entries(max_entries=1000)
        t_read = perf_counter()
        self.taps_folder.refresh()
        t_refresh = perf_counter()

        to_archive = {}
        writer = Batch()
        stats = BatchStats()
        paths = PathStatsAggregator()

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
                    data=tap_data,
                    tap_id=tap_filename,
                    batch_id=batch_id,
                    log_entry=log_entry,
                    writer=writer,
                    stats=stats,
                    paths=paths,
                )
                to_archive[tap_filename] = tap_data
            except Exception as e:
                logger.error(f"Error processing tap file {tap_filename}: {e}")

        t_process = perf_counter()

        flush_times: dict[str, float] = {}

        def do_flush(isolate: bool) -> None:
            t = perf_counter()
            writer.flush(tx, isolate=isolate)
            flush_times["rows"] = perf_counter() - t
            t = perf_counter()
            paths.flush(tx, isolate=isolate)
            flush_times["paths"] = perf_counter() - t
            t = perf_counter()
            stats.flush(tx)
            flush_times["stats"] = perf_counter() - t

        if PER_TABLE_TX:
            table_times = writer.flush_tables_timed(tx)
            flush_times["rows"] = sum(table_times.values())
            t = perf_counter()
            paths.flush(tx, isolate=False)
            tx.connection.commit()
            flush_times["paths"] = perf_counter() - t
            t = perf_counter()
            stats.flush(tx)
            tx.connection.commit()
            flush_times["stats"] = perf_counter() - t
            logger.info(
                "PER-TABLE flush: %s paths=%.0f stats=%.0f ms",
                " ".join(f"{name}={secs * 1000:.0f}" for name, secs in table_times.items()),
                flush_times["paths"] * 1000, flush_times["stats"] * 1000,
            )
        else:
            flush_with_isolation_fallback(tx, do_flush, writer.reset)
        t_flush = perf_counter()

        if new_entries:
            last_position = new_entries[-1].end_position
            self.access_log.write_last_processed_position(last_position)

        self.taps_folder.cleanup()
        t_cleanup = perf_counter()

        if new_entries:
            logger.info(
                "HTTP batch: entries=%d matched=%d | read=%.0f refresh=%.0f process=%.0f "
                "flush=%.0f (rows=%.0f paths=%.0f stats=%.0f) cleanup=%.0f | total=%.0f ms",
                len(new_entries), len(to_archive),
                (t_read - t_start) * 1000, (t_refresh - t_read) * 1000,
                (t_process - t_refresh) * 1000, (t_flush - t_process) * 1000,
                flush_times.get("rows", 0) * 1000, flush_times.get("paths", 0) * 1000,
                flush_times.get("stats", 0) * 1000, (t_cleanup - t_flush) * 1000,
                (t_cleanup - t_start) * 1000,
            )

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
        self.session_seq = 0

    def process_tap(
        self,
        data: dict,
        tap_id: str,
        batch_id: str,
        log_entry: dict,
        writer: Batch,
        stats: BatchStats,
        paths: PathStatsAggregator,
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

        request_ref = writer.insert(
            HttpRequestRow.Insert(
                port=port or 0,
                start_time=convert_datetime_to_timestamp(start_time),
                path=full_path,
                method=method or "",
                user_agent=user_agent,
                body=req_body,
                is_blocked=int(is_blocked),
                is_websocket=int(is_websocket),
                tap_id=tap_id,
                batch_id=batch_id,
                request_headers=serialize_headers(tap.request.headers),
            )
        )

        response_ref = writer.insert(
            HttpResponseRow.Insert(
                request_id=request_ref,
                status=status,
                body=resp_body,
                response_headers=serialize_headers(tap.response.headers),
            )
        )

        if not is_websocket:
            flags_written = list(find_body_flags(req_body or "", self.config.flag_format))
            flags_retrieved = list(find_body_flags(resp_body or "", self.config.flag_format))
            flag_rows = [
                FlagRow.Insert(
                    value=flag, http_request_id=request_ref, location="body", offset=offset
                )
                for offset, flag in flags_written
            ] + [
                FlagRow.Insert(
                    value=flag, http_response_id=response_ref, location="body", offset=offset
                )
                for offset, flag in flags_retrieved
            ]
            if flag_rows:
                writer.insert_many(flag_rows)
        else:
            flags_written = []
            flags_retrieved = []
        if port:
            stats.add_service(
                port=port,
                total_requests=1,
                total_responses=1 if not is_blocked else 0,
                total_blocked_requests=1 if is_blocked else 0,
                total_flags_written=len(flags_written),
                total_flags_retrieved=len(flags_retrieved),
            )
            stats.add_response_code(port=port, status_code=status, count=1)
            if not service_config or not any(
                re.fullmatch(ignored.path, path) and method == ignored.method
                for ignored in service_config.ignore_path_stats
            ):
                paths.record(port, path, full_path, request_ref, response_ref)
                stats.add_path_time(
                    port=port,
                    method=method,
                    path=path,
                    time=start_minute_ts,
                    count=1,
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
                    stats.add_query_param_time(
                        port=port,
                        param=param,
                        value=value,
                        time=start_minute_ts,
                        count=1,
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
                    stats.add_header_time(
                        port=port,
                        name=key,
                        value=value,
                        time=start_minute_ts,
                        count=1,
                    )

            stats.add_request_time(
                port=port,
                time=start_minute_ts,
                count=1,
                blocked_count=1 if is_blocked else 0,
            )

            if flags_written or flags_retrieved:
                stats.add_flag_time(
                    port=port,
                    time=start_minute_ts,
                    write_count=len(flags_written),
                    read_count=len(flags_retrieved),
                )

            self.session_seq += 1
            sessions = self.sessions.add_request(
                port=port,
                request_id=self.session_seq,
                start_time=start_time_ts,
                request_headers=tap.request.headers.values,
                response_headers=tap.response.headers.values,
            )
            for session_key in sessions:
                session_ref = writer.session(port, session_key)
                writer.insert(
                    SessionLinkRow.Insert(session_id=session_ref, http_request_id=request_ref)
                )

        if is_websocket:
            self.process_websocket(writer, tap, request_ref)

    def process_websocket(self, writer: Batch, tap: HttpTap, request_ref: Ref):
        connection_ref = writer.insert(
            WebSocketConnectionRow.Insert(http_request_id=request_ref)
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

        frame_rows = [
            WebSocketFrameRow.Insert(
                connection_id=connection_ref,
                ord=i,
                opcode=opcode.name,
                payload=payload,
                payload_text=payload.decode("utf-8", errors="ignore"),
                payload_size=len(payload),
                is_client=int(is_client),
            )
            for is_client, frames in ((True, request_frames), (False, response_frames))
            for i, (fin, opcode, payload) in enumerate(frames)
        ]

        if frame_rows:
            writer.insert_many(frame_rows)

    def decode_body(self, body_data: str | None) -> str | None:
        if body_data is None:
            return None

        return base64.b64decode(body_data).decode("utf-8", errors="ignore")
