import base64
import logging
import sqlite3
from datetime import datetime

from ctf_proxy.config.config import Config
from ctf_proxy.db.models import (
    FlagRow,
    ProxyStatsDB,
    ServiceStatsRow,
    TcpConnectionStatsRow,
)
from ctf_proxy.db.utils import convert_datetime_to_timestamp
from ctf_proxy.logs_processor.access_log import AccessLogReader
from ctf_proxy.logs_processor.flags import find_body_flags
from ctf_proxy.logs_processor.taps import TapsFolder
from ctf_proxy.logs_processor.utils import try_get_port_from_upstream_host

logger = logging.getLogger(__name__)


class TcpTapsFolder(TapsFolder):
    def __init__(self, path: str):
        super().__init__(path)
        self.trace_id_to_file: dict[int, str] = {}

    def on_file_loaded(self, filename: str, data: dict):
        connection_id = self.extract_trace_id_from_tap(filename, data)
        if connection_id is not None:
            self.trace_id_to_file[connection_id] = filename

    def extract_trace_id_from_tap(self, filename: str, data: dict) -> int | None:
        try:
            socket_trace = data.get("socket_buffered_trace", {})
            trace_id = socket_trace.get("trace_id")
            if trace_id and trace_id.isdigit():
                return int(trace_id)
        except Exception as e:
            logger.error(f"Error extracting connection ID from {filename}: {e}")

        logger.error(f"Could not extract connection ID from tap file {filename}")
        return None

    def pop_tap_filename_by_trace_id(self, connection_id: int) -> str | None:
        return self.trace_id_to_file.pop(connection_id, None)


class TcpProcessor:
    def __init__(self, db: ProxyStatsDB, config: Config, access_log_path: str, taps_dir: str):
        self.db = db
        self.config = config
        self.access_log = AccessLogReader(access_log_path)
        self.taps_folder = TcpTapsFolder(taps_dir)
        self.tap_processor = TcpTapProcessor(db, config)

    def process_new_access_log_entries(self, tx: sqlite3.Cursor, batch_id: str):
        new_entries = self.access_log.read_new_entries(max_entries=1000)
        self.taps_folder.refresh()

        to_archive = {}
        for entry in new_entries:
            log_entry = entry.data
            connection_id = log_entry.get("connection_id")
            if connection_id is None:
                # should not happen if access log is well-formed
                logger.warning(f"Access log entry missing connection_id: {log_entry}")
                continue

            tap_filename = self.taps_folder.pop_tap_filename_by_trace_id(connection_id)
            if not tap_filename:
                # tap files are written first, if it's missing, just skip it
                tap_filename = f"tcp_{connection_id}.json"
                logger.warning(f"Tap file not found for connection_id {connection_id}: {log_entry}")
                continue

            tap_data = self.taps_folder.pop_filename(tap_filename)
            if not tap_data:
                logger.warning(f"Tap data not loaded for file {tap_filename}")
                continue

            to_archive[tap_filename] = tap_data
            try:
                self.tap_processor.process_tap(
                    tx=tx,
                    data=tap_data,
                    tap_id=tap_filename,
                    batch_id=batch_id,
                    log_entry=log_entry,
                )
            except Exception as e:
                logger.error(f"Error processing tap file {tap_filename}: {e}")

        if new_entries:
            last_position = new_entries[-1].end_position
            self.access_log.write_last_processed_position(last_position)

        self.taps_folder.cleanup()
        return to_archive


class TcpTapProcessor:
    def __init__(self, db: ProxyStatsDB, config: Config):
        self.db = db
        self.config = config

    def process_tap(
        self, tx: sqlite3.Cursor, data: dict, tap_id: str, batch_id: str, log_entry: dict
    ):
        socket_trace = data.get("socket_buffered_trace", {})
        events = socket_trace.get("events", [])

        upstream_host = log_entry.get("upstream_host", "")
        port = try_get_port_from_upstream_host(upstream_host)

        start_time_str = log_entry.get("start_time")
        start_time = (
            datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
            if start_time_str
            else datetime.now()
        )
        start_time_ts = convert_datetime_to_timestamp(start_time)

        connection_id_from_log = log_entry.get("connection_id")
        bytes_in = log_entry.get("bytes_in", 0)
        bytes_out = log_entry.get("bytes_out", 0)
        duration_ms = log_entry.get("duration_ms", 0)
        is_blocked = log_entry.get("interceptor_message", "") == "blocked"

        total_read_bytes = 0
        total_write_bytes = 0
        all_read_data = bytearray()
        all_write_data = bytearray()
        flags_found = []

        for event in events:
            if "read" in event:
                read_data = event["read"]["data"]
                data_bytes = base64.b64decode(read_data.get("as_bytes", ""))
                total_read_bytes += len(data_bytes)
                all_read_data.extend(data_bytes)

                # Check for flags
                try:
                    data_text = data_bytes.decode("utf-8", errors="ignore")
                    for offset, flag in find_body_flags(data_text, self.config.flag_format):
                        flags_found.append(
                            ("read", offset + len(all_read_data) - len(data_bytes), flag)
                        )
                except Exception as e:
                    logger.error(f"Error processing read event in tap {tap_id}: {e}")

            elif "write" in event:
                write_data = event["write"]["data"]
                data_bytes = base64.b64decode(write_data.get("as_bytes", ""))
                total_write_bytes += len(data_bytes)
                all_write_data.extend(data_bytes)

                # Check for flags
                try:
                    data_text = data_bytes.decode("utf-8", errors="ignore")
                    for offset, flag in find_body_flags(data_text, self.config.flag_format):
                        flags_found.append(
                            ("write", offset + len(all_write_data) - len(data_bytes), flag)
                        )
                except Exception as e:
                    logger.error(f"Error processing write event in tap {tap_id}: {e}")

        tcp_connection_id = self.db.tcp_connections.insert(
            tx=tx,
            port=port,
            connection_id=connection_id_from_log or 0,
            start_time=start_time_ts,
            duration_ms=duration_ms,
            bytes_in=bytes_in,
            bytes_out=bytes_out,
            is_blocked=is_blocked,
            tap_id=tap_id,
            batch_id=batch_id,
        )

        for event in events:
            timestamp = int(
                datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).timestamp() * 1000
            )

            if "read" in event:
                read_data = event["read"]["data"]
                data_bytes = base64.b64decode(read_data.get("as_bytes", ""))
                truncated = read_data.get("truncated", False)

                self.db.tcp_events.insert(
                    tx=tx,
                    connection_id=tcp_connection_id,
                    timestamp=timestamp,
                    event_type="read",
                    data=data_bytes,
                    data_size=len(data_bytes),
                    truncated=truncated,
                )

            elif "write" in event:
                write_data = event["write"]["data"]
                data_bytes = base64.b64decode(write_data.get("as_bytes", ""))
                end_stream = event["write"].get("end_stream", False)
                truncated = write_data.get("truncated", False)

                self.db.tcp_events.insert(
                    tx=tx,
                    connection_id=tcp_connection_id,
                    timestamp=timestamp,
                    event_type="write",
                    data=data_bytes,
                    data_size=len(data_bytes),
                    end_stream=end_stream,
                    truncated=truncated,
                )

            elif "closed" in event:
                self.db.tcp_events.insert(
                    tx=tx,
                    connection_id=tcp_connection_id,
                    timestamp=timestamp,
                    event_type="closed",
                    data=b"",
                    data_size=0,
                    end_stream=True,
                    truncated=False,
                )

        # Insert flags
        if flags_found:
            flags_to_insert = [
                FlagRow.Insert(
                    value=flag,
                    tcp_connection_id=tcp_connection_id,
                    location=location,
                    offset=offset,
                )
                for location, offset, flag in flags_found
            ]
            self.db.flags.insert_many(tx=tx, flags=flags_to_insert)

        # Update service statistics
        if port:
            flags_written = sum(1 for loc, _, _ in flags_found if loc == "write")
            flags_retrieved = sum(1 for loc, _, _ in flags_found if loc == "read")

            self.db.service_stats.increment(
                tx,
                ServiceStatsRow.Increment(
                    port=port,
                    total_tcp_connections=1,
                    total_tcp_bytes_in=bytes_in,
                    total_tcp_bytes_out=bytes_out,
                    total_flags_written=flags_written,
                    total_flags_retrieved=flags_retrieved,
                ),
            )

            # Update TCP connection stats
            service = self.config.get_service_by_port(port)
            precision = service.tcp_connection_stats_precision if service else 100
            # Calculate buckets
            read_min = (total_read_bytes // precision) * precision
            read_max = read_min + precision
            write_min = (total_write_bytes // precision) * precision
            write_max = write_min + precision

            self.db.tcp_connection_stats.increment(
                tx,
                TcpConnectionStatsRow.Increment(
                    port=port,
                    read_min=read_min,
                    read_max=read_max,
                    write_min=write_min,
                    write_max=write_max,
                    count=1,
                ),
            )

            # Update time-based TCP connection stats (round to minute)
            time_bucket = (start_time_ts // 60000) * 60000

            tx.execute(
                """
                INSERT INTO tcp_connection_time_stats (port, read_min, read_max, write_min, write_max, time, count)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(port, read_min, read_max, write_min, write_max, time)
                DO UPDATE SET count = count + 1
            """,
                (port, read_min, read_max, write_min, write_max, time_bucket),
            )
