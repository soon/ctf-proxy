import time
from datetime import datetime

from ctf_proxy.db import ProxyStatsDB


class ServiceStats:
    def __init__(self, service_port: int, db: ProxyStatsDB):
        self.service_port = service_port
        self.db = db
        self._prev_stats = None

    def get_current_stats(self) -> dict:
        with self.db.connect() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """SELECT total_requests, total_blocked_requests, total_responses, total_blocked_responses,
                          total_flags_written, total_flags_retrieved, total_flags_blocked
                   FROM service_stats WHERE port = ?""",
                (self.service_port,),
            )
            service_stats_row = cursor.fetchone()

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

            cursor.execute(
                """SELECT status_code, count FROM http_response_code_stats
                   WHERE port = ? ORDER BY count DESC""",
                (self.service_port,),
            )
            status_counts = dict(cursor.fetchall())

            error_responses = sum(count for status, count in status_counts.items() if status >= 400)

            success_responses = sum(
                count for status, count in status_counts.items() if 200 <= status < 300
            )
            redirect_responses = sum(
                count for status, count in status_counts.items() if 300 <= status < 400
            )

            cursor.execute(
                """SELECT COUNT(DISTINCT path) FROM http_request WHERE port = ?""",
                (self.service_port,),
            )
            unique_paths = cursor.fetchone()[0]

            cursor.execute("""SELECT COUNT(*) FROM alert WHERE port = ?""", (self.service_port,))
            alerts_count = cursor.fetchone()[0]

            cursor.execute(
                """SELECT description, created FROM alert
                   WHERE port = ?
                   ORDER BY created DESC
                   LIMIT 5""",
                (self.service_port,),
            )
            recent_alerts = cursor.fetchall()

            cursor.execute(
                """SELECT COUNT(DISTINCT name), COUNT(DISTINCT value)
                   FROM http_header
                   JOIN http_request ON http_header.request_id = http_request.id
                   WHERE http_request.port = ?""",
                (self.service_port,),
            )
            header_stats = cursor.fetchone()
            unique_headers = header_stats[0] if header_stats else 0
            unique_header_values = header_stats[1] if header_stats else 0

            total_flags = flags_written + flags_retrieved

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
                "alerts_count": alerts_count,
                "recent_alerts": recent_alerts,
                "flags_written": flags_written,
                "flags_retrieved": flags_retrieved,
                "flags_blocked": flags_blocked,
                "total_flags": total_flags,
                "unique_headers": unique_headers,
                "unique_header_values": unique_header_values,
            }

    def get_deltas(self) -> tuple[dict, dict]:
        start_time = time.time()
        current = self.get_current_stats()

        if self._prev_stats is None:
            deltas = dict.fromkeys(current.keys(), 0)
            deltas["status_deltas"] = {}
            deltas["recent_alerts"] = []
        else:
            deltas = {}
            for key in current.keys():
                if key in ("status_counts", "recent_alerts"):
                    continue
                deltas[key] = current[key] - self._prev_stats.get(key, 0)

            deltas["status_deltas"] = {}
            for status, count in current["status_counts"].items():
                prev_count = self._prev_stats.get("status_counts", {}).get(status, 0)
                deltas["status_deltas"][status] = count - prev_count

            deltas["recent_alerts"] = current["recent_alerts"]

        self._prev_stats = current.copy()

        update_time = time.time() - start_time
        current["_debug_last_updated"] = datetime.now()
        current["_debug_update_time"] = update_time

        return current, deltas
