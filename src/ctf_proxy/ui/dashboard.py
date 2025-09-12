#!/usr/bin/env python3

import time
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.widgets import Footer, Header, Static

from ctf_proxy.config import Config
from ctf_proxy.db import ProxyStatsDB
from ctf_proxy.db.utils import convert_timestamp_to_datetime


class ServiceStats:
    def __init__(self, service_port: int, db: ProxyStatsDB):
        self.service_port = service_port
        self.db = db
        self._prev_stats = None

    def get_current_stats(self) -> dict:
        with self.db.connect() as conn:
            cursor = conn.cursor()

            # Get aggregated stats from service_stats table
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
                # Fallback if no stats row exists yet
                total_requests = blocked_requests = total_responses = blocked_responses = 0
                flags_written = flags_retrieved = flags_blocked = 0

            # Get HTTP response code stats from dedicated table
            cursor.execute(
                """SELECT status_code, count FROM http_response_code_stats
                   WHERE port = ? ORDER BY count DESC""",
                (self.service_port,),
            )
            status_counts = dict(cursor.fetchall())

            # Calculate error responses (4xx and 5xx) from response code stats
            error_responses = sum(count for status, count in status_counts.items() if status >= 400)

            # Get success rate stats
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

            # Get 5 most recent alerts
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

            # Copy recent_alerts as-is (no delta calculation needed)
            deltas["recent_alerts"] = current["recent_alerts"]

        self._prev_stats = current.copy()

        # Add debug info
        update_time = time.time() - start_time
        current["_debug_last_updated"] = datetime.now()
        current["_debug_update_time"] = update_time

        return current, deltas


class ServiceBlock(Static):
    DEFAULT_CSS = """
      ServiceBlock {
        border: solid cornflowerblue;
        width: 1fr;
        height: 1fr;
      }
    """

    def __init__(
        self, service_name: str, service_port: int, service_type: str, stats: ServiceStats
    ):
        self.service_name = service_name
        self.service_port = service_port
        self.service_type = service_type
        self.stats = stats
        super().__init__(id=f"service-{service_name}")

    def compose(self) -> ComposeResult:
        yield Static("", id=f"content-{self.service_name}")

    def on_mount(self) -> None:
        self.update_content()

    def update_content(self) -> None:
        current_time = datetime.now().strftime("%H:%M")
        current_stats, deltas = self.stats.get_deltas()

        # Debug info
        last_updated = current_stats.get("_debug_last_updated")
        update_time = current_stats.get("_debug_update_time", 0)
        debug_time = last_updated.strftime("%H:%M:%S") if last_updated else "N/A"
        debug_info = f"Updated: {debug_time} ({update_time * 1000:.1f}ms)"

        flags_written = current_stats.get("flags_written", 0)
        flags_retrieved = current_stats.get("flags_retrieved", 0)
        flags_blocked = current_stats.get("flags_blocked", 0)

        req_in = current_stats["total_requests"]
        req_in_delta = deltas["total_requests"]

        blocked_req = current_stats.get("blocked_requests", 0)
        blocked_req_delta = deltas.get("blocked_requests", 0)

        resp_out = current_stats["total_responses"]
        resp_out_delta = deltas["total_responses"]

        blocked_resp = current_stats.get("blocked_responses", 0)
        blocked_resp_delta = deltas.get("blocked_responses", 0)

        status_counts = current_stats["status_counts"]
        status_deltas = deltas["status_deltas"]

        # Show top 3 most frequent status codes
        if status_counts:
            top_statuses = sorted(status_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            status_line = ", ".join(
                [
                    f"{status}={count} ({status_deltas.get(status, 0):+d})"
                    for status, count in top_statuses
                ]
            )
        else:
            status_line = "No data"

        alerts_count = current_stats["alerts_count"]
        recent_alerts = current_stats["recent_alerts"]

        # Format recent alerts for display
        if recent_alerts:
            alerts_text = []
            for description, created in recent_alerts:
                # Parse timestamp and format it
                try:
                    alert_time = convert_timestamp_to_datetime(created)
                    time_str = alert_time.strftime("%H:%M")
                except Exception:
                    time_str = "??:??"

                # Truncate description if too long
                short_desc = description[:30] + "..." if len(description) > 30 else description
                alerts_text.append(f"  {time_str}: {short_desc}")

            alerts_display = f"⚠ Alerts ({alerts_count}):\n" + "\n".join(alerts_text)
        else:
            alerts_display = f"⚠ Alerts: {alerts_count}"

        header_delta = deltas["unique_headers"]
        header_values_delta = deltas["unique_header_values"]
        paths_delta = deltas["unique_paths"]

        content = f"""{self.service_name}:{self.service_port} [{self.service_type}] ⏱ {current_time}
🔧 {debug_info}

⚑ {flags_written} in | {flags_retrieved} out | {flags_blocked} ✖
⇢ {req_in} ({req_in_delta:+d}) in | {resp_out} ({resp_out_delta:+d}) out
✖ {blocked_req} ({blocked_req_delta:+d}) in | {blocked_resp} ({blocked_resp_delta:+d}) out
↩ {status_line}

{alerts_display}
+ Headers: {header_delta:+d} | + Values: {header_values_delta:+d} | + Paths: {paths_delta:+d}"""

        content_widget = self.query_one(f"#content-{self.service_name}")
        content_widget.update(content)


class Dashboard(Widget):
    DEFAULT_CSS = """
      Dashboard {
        layout: grid;
        grid-size: 3;
      }
    """

    def __init__(self, config: Config, db: ProxyStatsDB):
        self.config = config
        self.db = db
        self.service_blocks = []
        super().__init__()

    def compose(self) -> ComposeResult:
        for service in self.config.services:
            stats = ServiceStats(service.port, self.db)
            block = ServiceBlock(service.name, service.port, service.type.value, stats)
            self.service_blocks.append(block)
            yield block

    def on_mount(self) -> None:
        self.set_interval(5.0, self.refresh_data)

    def refresh_data(self) -> None:
        for block in self.service_blocks:
            block.update_content()


class CTFProxyDashboard(App):
    def __init__(self, config: Config, db_path: str):
        self.config = config
        self.db = ProxyStatsDB(db_path)
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Dashboard(
            self.config,
            self.db,
        )
        yield Footer()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="CTF Proxy Dashboard")
    parser.add_argument(
        "--config", default="config.yml", help="Path to configuration file (default: config.yml)"
    )
    parser.add_argument(
        "--db",
        default="proxy_stats.db",
        help="Path to database file (default: proxy_stats.db)",
    )

    args = parser.parse_args()

    config_path = Path(args.config)
    db_path = Path(args.db)

    if not config_path.exists():
        print(f"Error: Configuration file not found: {config_path}")
        print("Please create a config file or specify the correct path with --config")
        return 1

    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        print("Please ensure the logs processor has created the database")
        return 1

    with Config(config_path) as config:
        config.start_watching()
        app = CTFProxyDashboard(config, str(db_path))
        app.run()


if __name__ == "__main__":
    exit(main())
