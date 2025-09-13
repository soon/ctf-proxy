from datetime import datetime

from textual.events import Click
from textual.message import Message
from textual.widgets import Static

from ctf_proxy.db.utils import convert_timestamp_to_datetime

from .service_stats import ServiceStats


class ServiceBlock(Static):
    DEFAULT_CSS = """
      ServiceBlock {
        border: solid cornflowerblue;
        width: 1fr;
        height: 1fr;
      }
      ServiceBlock:hover {
        border: solid yellow;
      }
    """

    class Clicked(Message):
        def __init__(self, service_name: str, service_port: int, service_type: str) -> None:
            self.service_name = service_name
            self.service_port = service_port
            self.service_type = service_type
            super().__init__()

    def __init__(
        self, service_name: str, service_port: int, service_type: str, stats: ServiceStats
    ):
        self.service_name = service_name
        self.service_port = service_port
        self.service_type = service_type
        self.stats = stats
        super().__init__(id=f"service-{service_name}")

    def compose(self):
        yield Static("", id=f"content-{self.service_name}")

    def on_mount(self) -> None:
        self.update_content()

    def on_click(self, event: Click) -> None:
        self.post_message(self.Clicked(self.service_name, self.service_port, self.service_type))

    def _on_click(self, event: Click) -> None:
        self.post_message(self.Clicked(self.service_name, self.service_port, self.service_type))

    def update_content(self) -> None:
        current_time = datetime.now().strftime("%H:%M")
        current_stats, deltas = self.stats.get_deltas()

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

        if recent_alerts:
            alerts_text = []
            for description, created in recent_alerts:
                try:
                    alert_time = convert_timestamp_to_datetime(created)
                    time_str = alert_time.strftime("%H:%M")
                except Exception:
                    time_str = "??:??"

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
