import time
from datetime import datetime

from ctf_proxy.db import ProxyStatsDB
from ctf_proxy.db.dashboard_queries import DashboardQueries


class ServiceStats:
    def __init__(self, service_port: int, db: ProxyStatsDB):
        self.service_port = service_port
        self.db = db
        self.queries = DashboardQueries()
        self._prev_stats = None

    def get_current_stats(self) -> dict:
        with self.db.connect() as conn:
            cursor = conn.cursor()

            service_stats_row = self.queries.service_stats_for_port(cursor, self.service_port)

            if service_stats_row:
                (
                    total_requests,
                    blocked_requests,
                    total_responses,
                    blocked_responses,
                    flags_written,
                    flags_retrieved,
                    flags_blocked,
                ) = service_stats_row
            else:
                total_requests = blocked_requests = total_responses = blocked_responses = 0
                flags_written = flags_retrieved = flags_blocked = 0

            status_counts = dict(
                self.queries.response_code_counts_for_port(cursor, self.service_port)
            )

            error_responses = sum(count for status, count in status_counts.items() if status >= 400)

            success_responses = sum(
                count for status, count in status_counts.items() if 200 <= status < 300
            )
            redirect_responses = sum(
                count for status, count in status_counts.items() if 300 <= status < 400
            )

            # Use pre-calculated stats from http_path_stats instead of counting distinct paths
            unique_paths = self.queries.distinct_path_count_for_port(cursor, self.service_port)[0]

            # Use pre-calculated stats from http_header_time_stats
            header_stats = self.queries.header_distinct_counts_for_port(cursor, self.service_port)
            unique_headers = header_stats[0] if header_stats and header_stats[0] else 0
            unique_header_values = header_stats[1] if header_stats and header_stats[1] else 0

            total_flags = flags_written + flags_retrieved

            # Get TCP stats if this is a TCP service
            tcp_stats = None
            tcp_row = self.queries.tcp_stats_for_port(cursor, self.service_port)
            if tcp_row:  # If there are TCP stats
                tcp_stats = {
                    "total_connections": tcp_row[0],
                    "total_bytes_in": tcp_row[1],
                    "total_bytes_out": tcp_row[2],
                    "avg_duration_ms": tcp_row[3],
                    "total_flags_found": tcp_row[4],
                }

            return {
                "total_requests": total_requests,
                "blocked_requests": blocked_requests,
                "total_responses": total_responses,
                "blocked_responses": blocked_responses,
                "error_responses": error_responses,
                "success_responses": success_responses,
                "redirect_responses": redirect_responses,
                "status_counts": status_counts,
                "unique_paths": unique_paths,
                "flags_written": flags_written,
                "flags_retrieved": flags_retrieved,
                "flags_blocked": flags_blocked,
                "total_flags": total_flags,
                "unique_headers": unique_headers,
                "unique_header_values": unique_header_values,
                "tcp_stats": tcp_stats,
            }

    def get_deltas(self) -> tuple[dict, dict]:
        start_time = time.time()
        current = self.get_current_stats()

        if self._prev_stats is None:
            deltas = dict.fromkeys(current.keys(), 0)
            deltas["status_deltas"] = {}
        else:
            deltas = {}
            for key in current.keys():
                if key == "status_counts":
                    continue
                deltas[key] = current[key] - self._prev_stats.get(key, 0)

            deltas["status_deltas"] = {}
            for status, count in current["status_counts"].items():
                prev_count = self._prev_stats.get("status_counts", {}).get(status, 0)
                deltas["status_deltas"][status] = count - prev_count

        self._prev_stats = current.copy()

        update_time = time.time() - start_time
        current["_debug_last_updated"] = datetime.now()
        current["_debug_update_time"] = update_time

        return current, deltas
