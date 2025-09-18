import time
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Input, Static

from ctf_proxy.config import Service
from ctf_proxy.db import ProxyStatsDB
from ctf_proxy.db.utils import convert_timestamp_to_datetime

from .service_stats import ServiceStats


def parse_filter(filter_str: str) -> tuple[str, list]:
    """
    Parse filter string into SQL WHERE clause and parameters.

    Supports:
    - column=value (equality)
    - column=^value (starts with)
    - column=$value (ends with)
    - value (auto-infer column from value)

    Auto-inference rules:
    - Starts with / -> path
    - Number (100-599) -> status
    - GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS -> method
    - Otherwise -> path (contains)

    Supported columns: path, method, status, user_agent, blocked
    """
    HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
    VALID_COLUMNS = {"path", "method", "status", "user_agent", "blocked"}

    filter_str = filter_str.strip()
    if not filter_str:
        return "", []

    # Check if explicit column specified
    if "=" in filter_str:
        parts = filter_str.split("=", 1)
        if len(parts) == 2:
            column, value = parts[0].strip(), parts[1].strip()

            # Handle operators
            if value.startswith("^"):
                # Starts with
                value = value[1:]
                if column in VALID_COLUMNS:
                    return f"req.{column} LIKE ?", [f"{value}%"]
                return "", []
            elif value.startswith("$"):
                # Ends with
                value = value[1:]
                if column in VALID_COLUMNS:
                    return f"req.{column} LIKE ?", [f"%{value}"]
                return "", []
            else:
                # Equality
                if column in VALID_COLUMNS:
                    if column == "status":
                        # For status, handle response table
                        return "resp.status = ?", [value]
                    elif column == "blocked":
                        # Handle blocked as boolean
                        if value.lower() in ("yes", "true", "1"):
                            return "req.is_blocked = 1", []
                        elif value.lower() in ("no", "false", "0"):
                            return "req.is_blocked = 0", []
                        else:
                            return "", []
                    return f"req.{column} = ?", [value]
                return "", []

    # Auto-inference for value without explicit column
    value = filter_str

    # Path: starts with /
    if value.startswith("/"):
        return "req.path = ?", [value]

    # Status: numeric 100-599
    if value.isdigit():
        status_code = int(value)
        if 100 <= status_code <= 599:
            return "resp.status = ?", [status_code]

    # Method: known HTTP methods
    if value.upper() in HTTP_METHODS:
        return "req.method = ?", [value.upper()]

    # Default: treat as path contains
    return "req.path LIKE ?", [f"%{value}%"]


class ServiceDetailScreen(Screen):
    DEFAULT_CSS = """
      ServiceDetailScreen {
        align: center middle;
      }

      .service-detail-container {
        background: $surface;
        border: thick $primary;
        width: 95%;
        height: 95%;
        padding: 1;
      }

      .service-header {
        height: 3;
        margin-bottom: 1;
      }

      .service-stats {
        height: 8;
        margin-bottom: 1;
        border: solid $primary;
        padding: 1;
      }

      .requests-table {
        height: 1fr;
      }

      .command-input {
        height: 3;
        dock: bottom;
        border: solid $primary;
        margin-top: 1;
      }
    """

    BINDINGS = [
        ("escape", "dismiss", "Close Screen"),
        ("question_mark", "show_help", "Show Help"),
        ("q", "view_query_param_stats", "View Query Param Stats"),
        ("h", "view_header_stats", "View Header Stats"),
        ("r", "refresh", "Refresh Table"),
        ("p", "view_path_stats", "View Path Stats"),
        ("enter", "view_request", "View Request Details"),
        ("/", "focus_command", "Focus Command Input"),
    ]

    def __init__(self, service: Service, db: ProxyStatsDB):
        self.service = service
        self.db = db
        self.stats = ServiceStats(service.port, db)
        self.filter_where_clause = ""
        self.filter_params = []
        self.filter_display = None
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical(classes="service-detail-container"):
            yield Static(
                f"Service: {self.service.name}:{self.service.port} [{self.service.type.value}] - Press '?' for help, 'r' to refresh, 'p' for paths, 'q' for query params, 'h' for headers, Enter to view request, ESC to close",
                classes="service-header",
            )
            yield Static("", id="service-stats", classes="service-stats")
            yield self._create_requests_table()
            yield Input(
                placeholder="Enter command (e.g., q path=/api, q 404, q POST, ? for help)",
                classes="command-input",
                id="command-input",
            )

    def action_refresh(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self._populate_requests_table(table)

    def action_show_help(self) -> None:
        """Show help in a toast notification"""
        help_text = """Commands:
q <filter> - Filter requests (e.g., q path=/api, q 404, q POST)
clear/c - Clear filter
? - Show help
r - Refresh
p - Show paths
q - Show query params
h - Show headers"""
        self.app.notify(help_text, severity="information")

    def action_focus_command(self) -> None:
        """Focus the command input"""
        command_input = self.query_one("#command-input", Input)
        command_input.focus()

    def action_view_request(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row is not None:
            row = table.get_row_at(table.cursor_row)
            request_id = int(row[0])
            from .request_detail_screen import RequestDetailScreen

            self.app.push_screen(RequestDetailScreen(request_id, self.db))

    def action_view_path_stats(self) -> None:
        """View path stats for this service port"""
        from .path_stats_screen import PathStatsScreen

        self.app.push_screen(PathStatsScreen(self.db, self.service))

    def action_view_query_param_stats(self) -> None:
        """View query parameter stats for this service port"""
        from .query_param_stats_screen import QueryParamStatsScreen

        self.app.push_screen(QueryParamStatsScreen(self.db, self.service))

    def action_view_header_stats(self) -> None:
        """View header stats for this service port"""
        from .header_stats_screen import HeaderStatsScreen

        self.app.push_screen(HeaderStatsScreen(self.db, self.service))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row = event.data_table.get_row_at(event.cursor_row)
        request_id = int(row[0])
        from .request_detail_screen import RequestDetailScreen

        self.app.push_screen(RequestDetailScreen(request_id, self.db))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value.strip()
        input_widget = event.input

        if command.startswith("q "):
            # Parse q command with the new intelligent parser
            filter_str = command[2:].strip()
            where_clause, params = parse_filter(filter_str)

            if where_clause:
                self.filter_where_clause = where_clause
                self.filter_params = params
                self.filter_display = filter_str
                self.app.notify(f"Applied filter: {filter_str}", severity="information")
                self.action_refresh()
            else:
                input_widget.value = "Error: Invalid filter format"
                self.set_timer(3.0, lambda: setattr(input_widget, "value", ""))
        elif command == "clear" or command == "c":
            self.filter_where_clause = ""
            self.filter_params = []
            self.filter_display = None
            input_widget.value = "Filter cleared"
            self.action_refresh()
            self.set_timer(2.0, lambda: setattr(input_widget, "value", ""))
        elif command.startswith("?") or command == "/" or command == "h":
            available_commands = [
                "q <filter> - Filter requests (see examples below)",
                "Examples:",
                "  q path=/api/users (exact path)",
                "  q path=^/api (starts with /api)",
                "  q path=$json (ends with json)",
                "  q method=POST (exact method)",
                "  q status=404 (exact status)",
                "  q blocked=yes (show blocked requests)",
                "  q blocked=no (show non-blocked requests)",
                "  q /api/users (auto: exact path)",
                "  q 404 (auto: status)",
                "  q POST (auto: method)",
                "clear or c - Clear current filter",
                "? - Show this help",
                "r - Refresh table",
                "p - View path stats",
                "q - View query param stats",
                "h - View header stats",
            ]
            input_widget.value = f"Commands: {' | '.join(available_commands)}"
            self.set_timer(8.0, lambda: setattr(input_widget, "value", ""))
        else:
            self.app.notify("Unknown command. Type ? for help", severity="error")

    def refresh_stats(self) -> None:
        current_time = datetime.now().strftime("%H:%M:%S")
        current_stats, deltas = self.stats.get_deltas()

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

        error_responses = current_stats.get("error_responses", 0)
        error_responses_delta = deltas.get("error_responses", 0)

        success_responses = current_stats.get("success_responses", 0)
        success_responses_delta = deltas.get("success_responses", 0)

        alerts_count = current_stats["alerts_count"]
        unique_paths = current_stats["unique_paths"]
        unique_headers = current_stats["unique_headers"]

        paths_delta = deltas["unique_paths"]
        headers_delta = deltas["unique_headers"]
        alerts_delta = deltas["alerts_count"]

        filter_info = f" | Filter: {self.filter_display}" if self.filter_display else ""

        stats_content = f"""📊 Live Stats (Updated: {current_time}){filter_info}
🏴 Flags: {flags_written} written | {flags_retrieved} retrieved | {flags_blocked} blocked
📨 Requests: {req_in} total ({req_in_delta:+d}) | {blocked_req} blocked ({blocked_req_delta:+d})
📤 Responses: {resp_out} total ({resp_out_delta:+d}) | {blocked_resp} blocked ({blocked_resp_delta:+d})
✅ Success: {success_responses} ({success_responses_delta:+d}) | ❌ Errors: {error_responses} ({error_responses_delta:+d})
🛣️  Unique Paths: {unique_paths} ({paths_delta:+d}) | 📋 Headers: {unique_headers} ({headers_delta:+d}) | ⚠️  Alerts: {alerts_count} ({alerts_delta:+d})"""

        stats_widget = self.query_one("#service-stats")
        stats_widget.update(stats_content)

    def on_mount(self) -> None:
        self.set_interval(2.0, self.refresh_stats)
        self.refresh_stats()

    def _create_requests_table(self) -> DataTable:
        table = DataTable(classes="requests-table", cursor_type="row")
        table.add_columns(
            "ID",
            "Time",
            "Method",
            "Path",
            "Status",
            "Blocked",
            "User-Agent",
            "Req Flags",
            "Resp Flags",
            "In Links",
            "Out Links",
        )
        self._populate_requests_table(table)
        return table

    def _populate_requests_table(self, table: DataTable) -> None:
        start_time = time.time()

        with self.db.connect() as conn:
            cursor = conn.cursor()

            # Build the query with optional filter
            base_query = """
                SELECT
                    req.id,
                    req.start_time,
                    req.method,
                    req.path,
                    resp.status,
                    req.is_blocked,
                    req.user_agent,
                    (SELECT COUNT(*) FROM flag WHERE flag.http_request_id = req.id) as req_flags_count,
                    (SELECT COUNT(*) FROM flag WHERE flag.http_response_id = resp.id) as resp_flags_count,
                    (SELECT COUNT(*) FROM http_request_link WHERE to_request_id = req.id) as incoming_links_count,
                    (SELECT COUNT(*) FROM http_request_link WHERE from_request_id = req.id) as outgoing_links_count
                FROM http_request req
                LEFT JOIN http_response resp ON req.id = resp.request_id
                WHERE req.port = ?
            """

            params = [self.service.port]

            if self.filter_where_clause:
                base_query += f" AND {self.filter_where_clause}"
                params.extend(self.filter_params)

            base_query += """
                ORDER BY req.start_time DESC
                LIMIT 100
            """

            cursor.execute(base_query, params)

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
                    req_flags_count,
                    resp_flags_count,
                    incoming_links_count,
                    outgoing_links_count,
                ) = row

                try:
                    time_dt = convert_timestamp_to_datetime(start_time)
                    time_str = time_dt.strftime("%H:%M:%S")
                except Exception:
                    time_str = "??:??:??"

                status_str = str(status) if status else "N/A"
                blocked_str = "REQ-BLOCKED" if is_blocked else ""
                user_agent_str = (
                    (user_agent[:30] + "...")
                    if user_agent and len(user_agent) > 30
                    else (user_agent or "")
                )

                req_flags = req_flags_count or 0
                resp_flags = resp_flags_count or 0

                req_flags_str = ""
                if req_flags > 0:
                    if req_flags == 1:
                        req_flags_str = "HAS FLAG"
                    else:
                        req_flags_str = f"HAS {req_flags} FLAGS"

                resp_flags_str = ""
                if resp_flags > 0:
                    if resp_flags == 1:
                        resp_flags_str = "HAS FLAG"
                    else:
                        resp_flags_str = f"HAS {resp_flags} FLAGS"

                incoming_links = incoming_links_count or 0
                outgoing_links = outgoing_links_count or 0

                incoming_links_str = str(incoming_links) if incoming_links > 0 else ""
                outgoing_links_str = str(outgoing_links) if outgoing_links > 0 else ""

                path_str = path[:50] + "..." if len(path) > 50 else path

                table.add_row(
                    str(req_id),
                    time_str,
                    method,
                    path_str,
                    status_str,
                    blocked_str,
                    user_agent_str,
                    req_flags_str,
                    resp_flags_str,
                    incoming_links_str,
                    outgoing_links_str,
                )

    def action_dismiss(self) -> None:
        self.dismiss()
