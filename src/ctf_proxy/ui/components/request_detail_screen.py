from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Label, Static

from ctf_proxy.db import ProxyStatsDB
from ctf_proxy.db.utils import convert_timestamp_to_datetime


class RequestDetailScreen(Screen):
    DEFAULT_CSS = """
      RequestDetailScreen {
        align: center middle;
      }

      .request-detail-container {
        background: $surface;
        border: thick $primary;
        width: 95%;
        height: 95%;
        padding: 1;
      }

      .request-header {
        height: 3;
        margin-bottom: 1;
      }

      .panels-container {
        height: 1fr;
        layout: horizontal;
      }

      .request-panel {
        width: 1fr;
        margin-right: 1;
        border: solid $accent;
        padding: 1;
      }

      .response-panel {
        width: 1fr;
        border: solid $warning;
        padding: 1;
      }

      .panel-title {
        height: 1;
        text-style: bold;
        margin-bottom: 1;
      }

      .section-title {
        height: 1;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 1;
      }

      .scrollable-content {
        height: 1fr;
        scrollbar-gutter: stable;
      }

      .data-table {
        margin-bottom: 1;
        height: auto;
        min-height: 5;
      }

      .body-content {
        border: solid $primary;
        padding: 1;
        margin-bottom: 1;
        height: auto;
        min-height: 3;
        max-height: 15;
        scrollbar-gutter: stable;
      }

      .query-params-table {
        margin-bottom: 1;
        height: auto;
        min-height: 3;
        max-height: 8;
      }

      .request-flags-table {
        margin-top: 1;
        height: auto;
        min-height: 3;
        max-height: 8;
      }

      .response-flags-table {
        margin-top: 1;
        height: auto;
        min-height: 3;
        max-height: 8;
      }
    """

    BINDINGS = [
        ("escape", "dismiss", "Back"),
        ("q", "dismiss", "Quit"),
    ]

    def __init__(self, request_id: int, db: ProxyStatsDB):
        self.request_id = request_id
        self.db = db
        self.request_data = None
        self.response_data = None
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical(classes="request-detail-container"):
            yield Static(
                f"Request ID: {self.request_id} - Press ESC to go back",
                classes="request-header",
                id="header-info",
            )
            with Horizontal(classes="panels-container"):
                with Vertical(classes="request-panel"):
                    yield Label("📤 REQUEST", classes="panel-title")
                    with ScrollableContainer(classes="scrollable-content"):
                        yield Static("", id="request-basic-info")
                        yield Label("Headers:", classes="section-title")
                        yield self._create_request_headers_table()
                        yield Label(
                            "Query Parameters:", classes="section-title", id="query-params-label"
                        )
                        yield self._create_query_params_table()
                        yield Label("Request Body:", classes="section-title")
                        yield ScrollableContainer(
                            Static("", id="request-body"), classes="body-content"
                        )
                        yield Label(
                            "Flags Found:", classes="section-title", id="request-flags-label"
                        )
                        yield self._create_request_flags_table()

                with Vertical(classes="response-panel"):
                    yield Label("📥 RESPONSE", classes="panel-title")
                    with ScrollableContainer(classes="scrollable-content"):
                        yield Static("", id="response-basic-info")
                        yield Label("Headers:", classes="section-title")
                        yield self._create_response_headers_table()
                        yield Label("Response Body:", classes="section-title")
                        yield ScrollableContainer(
                            Static("", id="response-body"), classes="body-content"
                        )
                        yield Label(
                            "Flags Found:", classes="section-title", id="response-flags-label"
                        )
                        yield self._create_response_flags_table()

    def on_mount(self) -> None:
        self._load_request_response_data()

    def _load_request_response_data(self) -> None:
        with self.db.connect() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    req.method,
                    req.path,
                    req.body,
                    req.user_agent,
                    req.start_time,
                    req.port,
                    resp.status,
                    resp.body as response_body,
                    resp.id as response_id
                FROM http_request req
                LEFT JOIN http_response resp ON req.id = resp.request_id
                WHERE req.id = ?
                """,
                (self.request_id,),
            )

            row = cursor.fetchone()
            if row:
                (
                    method,
                    path,
                    body,
                    user_agent,
                    start_time,
                    port,
                    status,
                    response_body,
                    response_id,
                ) = row

                self.request_data = {
                    "method": method,
                    "path": path,
                    "body": body,
                    "user_agent": user_agent,
                    "start_time": start_time,
                    "port": port,
                }

                self.response_data = (
                    {"status": status, "body": response_body, "id": response_id}
                    if status is not None
                    else None
                )

                self._update_header_info()
                self._update_request_info()
                self._update_response_info()
                self._update_request_body()
                self._update_response_body()
                self._check_and_hide_query_params()
                self._check_and_hide_flags()

    def _update_header_info(self) -> None:
        if self.request_data:
            header_text = f"Request ID: {self.request_id} | Port: {self.request_data['port']} - Press ESC to go back"
        else:
            header_text = f"Request ID: {self.request_id} - Press ESC to go back"

        header_widget = self.query_one("#header-info")
        header_widget.update(header_text)

    def _update_request_info(self) -> None:
        if not self.request_data:
            info_content = f"Request {self.request_id} not found"
        else:
            try:
                start_dt = convert_timestamp_to_datetime(self.request_data["start_time"])
                start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                start_str = "Unknown"

            user_agent_str = self.request_data["user_agent"] or "None"

            # Parse path to get just the path part (without query params)
            path = self.request_data["path"]
            if "?" in path:
                path_part, _ = path.split("?", 1)
            else:
                path_part = path

            info_content = f"""{self.request_data["method"]} {path_part}
Timestamp: {start_str}
User-Agent: {user_agent_str}"""

        info_widget = self.query_one("#request-basic-info")
        info_widget.update(info_content)

    def _update_response_info(self) -> None:
        if not self.response_data:
            info_content = "No response data available"
        else:
            status_str = str(self.response_data["status"])
            info_content = f"""Status Code: {status_str}
Response Available: Yes"""

        info_widget = self.query_one("#response-basic-info")
        info_widget.update(info_content)

    def _update_request_body(self) -> None:
        body = self.request_data["body"] if self.request_data else None
        body_content = body if body else "No request body"

        # Don't truncate unless extremely large (>10KB)
        if body and len(body) > 10000:
            body_content = (
                body[:10000] + f"\n\n... [Content truncated. Full size: {len(body)} bytes]"
            )

        body_widget = self.query_one("#request-body")
        body_widget.update(body_content)

    def _update_response_body(self) -> None:
        if not self.response_data:
            body_content = "No response data available"
        else:
            body = self.response_data["body"]
            body_content = body if body else "No response body"

            # Don't truncate unless extremely large (>10KB)
            if body and len(body) > 10000:
                body_content = (
                    body[:10000] + f"\n\n... [Content truncated. Full size: {len(body)} bytes]"
                )

        body_widget = self.query_one("#response-body")
        body_widget.update(body_content)

    def _check_and_hide_query_params(self) -> None:
        """Hide query parameters section if no parameters exist"""
        if not self.request_data:
            return

        path = self.request_data["path"]
        has_params = "?" in path and len(path.split("?", 1)[1].strip()) > 0

        if not has_params:
            try:
                label = self.query_one("#query-params-label")
                label.display = False
                table = self.query_one(".query-params-table")
                table.display = False
            except Exception:
                pass  # Widgets might not exist yet

    def _check_and_hide_flags(self) -> None:
        """Hide flag sections if no flags exist"""
        with self.db.connect() as conn:
            cursor = conn.cursor()

            # Check for request flags
            cursor.execute(
                "SELECT COUNT(*) FROM flag WHERE http_request_id = ?", (self.request_id,)
            )
            request_flag_count = cursor.fetchone()[0]

            if request_flag_count == 0:
                try:
                    label = self.query_one("#request-flags-label")
                    label.display = False
                    table = self.query_one(".request-flags-table")
                    table.display = False
                except Exception:
                    pass

            # Check for response flags
            cursor.execute(
                """SELECT COUNT(*)
                   FROM flag f
                   INNER JOIN http_response r ON f.http_response_id = r.id
                   WHERE r.request_id = ?""",
                (self.request_id,),
            )
            response_flag_count = cursor.fetchone()[0]

            if response_flag_count == 0:
                try:
                    label = self.query_one("#response-flags-label")
                    label.display = False
                    table = self.query_one(".response-flags-table")
                    table.display = False
                except Exception:
                    pass

    def _create_request_headers_table(self) -> DataTable:
        table = DataTable(classes="data-table")
        table.add_columns("Header Name", "Value")

        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT name, value
                FROM http_header
                WHERE request_id = ?
                ORDER BY name
                """,
                (self.request_id,),
            )

            for name, value in cursor.fetchall():
                # Don't truncate header values unless extremely long
                display_value = value
                if len(value) > 200:
                    display_value = value[:200] + f"... [truncated, full length: {len(value)}]"
                table.add_row(name, display_value)

        return table

    def _create_response_headers_table(self) -> DataTable:
        table = DataTable(classes="data-table")
        table.add_columns("Header Name", "Value")

        # First check if there's any response at all
        with self.db.connect() as conn:
            cursor = conn.cursor()

            # Get response ID directly from database
            cursor.execute("SELECT id FROM http_response WHERE request_id = ?", (self.request_id,))
            response_row = cursor.fetchone()

            if not response_row:
                table.add_row("No Response", "No response data available")
                return table

            response_id = response_row[0]

            # Now get headers for this response
            cursor.execute(
                """
                SELECT name, value
                FROM http_header
                WHERE response_id = ?
                ORDER BY name
                """,
                (response_id,),
            )

            rows = cursor.fetchall()
            if not rows:
                table.add_row("No Headers", "No response headers found")
            else:
                for name, value in rows:
                    # Don't truncate header values unless extremely long
                    display_value = value
                    if len(value) > 200:
                        display_value = value[:200] + f"... [truncated, full length: {len(value)}]"
                    table.add_row(name, display_value)

        return table

    def _create_query_params_table(self) -> DataTable:
        table = DataTable(classes="query-params-table")
        table.add_columns("Parameter", "Value")

        if not self.request_data:
            table.add_row("No Data", "No request data available")
            return table

        path = self.request_data["path"]
        if "?" not in path:
            table.add_row("No Parameters", "No query parameters found")
            return table

        _, query_string = path.split("?", 1)
        params = []

        # Parse query parameters
        for param_pair in query_string.split("&"):
            if "=" in param_pair:
                key, value = param_pair.split("=", 1)
                params.append((key, value))
            else:
                params.append((param_pair, ""))

        if not params:
            table.add_row("No Parameters", "No query parameters found")
        else:
            for key, value in params:
                # URL decode for display
                try:
                    from urllib.parse import unquote

                    key = unquote(key)
                    value = unquote(value)
                except Exception:
                    pass  # Keep original if decoding fails

                # Don't truncate unless extremely long
                display_value = value
                if len(value) > 200:
                    display_value = value[:200] + f"... [truncated, full length: {len(value)}]"

                table.add_row(key, display_value)

        return table

    def _create_request_flags_table(self) -> DataTable:
        table = DataTable(classes="request-flags-table")
        table.add_columns("Flag", "Location")

        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT value, location
                FROM flag
                WHERE http_request_id = ?
                ORDER BY value
                """,
                (self.request_id,),
            )

            rows = cursor.fetchall()
            if not rows:
                table.add_row("No flags found", "N/A")
            else:
                for flag_value, location in rows:
                    location_str = location if location else "N/A"
                    table.add_row(flag_value, location_str)

        return table

    def _create_response_flags_table(self) -> DataTable:
        table = DataTable(classes="response-flags-table")
        table.add_columns("Flag", "Location")

        with self.db.connect() as conn:
            cursor = conn.cursor()

            # Get response flags using a more reliable query
            cursor.execute(
                """
                SELECT f.value, f.location
                FROM flag f
                INNER JOIN http_response r ON f.http_response_id = r.id
                WHERE r.request_id = ?
                ORDER BY f.value
                """,
                (self.request_id,),
            )

            rows = cursor.fetchall()
            if not rows:
                table.add_row("No flags found", "N/A")
            else:
                for flag_value, location in rows:
                    location_str = location if location else "N/A"
                    table.add_row(flag_value, location_str)

        return table

    def action_dismiss(self) -> None:
        self.dismiss()
