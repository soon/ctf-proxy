import time

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Sparkline, Static

from ctf_proxy.config import Service
from ctf_proxy.db import ProxyStatsDB

from .path_stats import PathStats


class PathStatsScreen(Screen):
    DEFAULT_CSS = """
      PathStatsScreen {
        align: center middle;
      }

      .path-stats-container {
        width: 100%;
        height: 100%;
        padding: 0 1;
      }

      .header-section {
        height: auto;
        margin-bottom: 1;
      }

      .scrollable-content {
        height: 1fr;
      }

      .path-line {
        layout: horizontal;
        height: 1;
        margin: 0;
      }

      .path-label {
        width: 50;
        color: $accent;
        text-style: bold;
      }

      .method-label {
        width: 8;
        color: $primary;
        text-style: bold;
      }

      .count-label {
        width: 10;
        text-align: right;
        color: $primary;
      }

      .sparkline-widget {
        width: 60;
        margin-left: 2;
      }

      .title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
      }

      .port-info {
        text-align: center;
        color: $accent;
        margin-bottom: 1;
      }

      .time-info {
        text-align: center;
        color: $secondary;
        margin-bottom: 1;
      }

      .ignored-info {
        text-align: center;
        color: $warning;
        text-style: italic;
        margin-bottom: 1;
      }

      .time-info {
        text-align: center;
        color: $secondary;
        margin-bottom: 1;
        text-style: italic;
      }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self, db: ProxyStatsDB, service: Service):
        self.db = db
        self.service = service
        self.port = service.port
        self.path_stats = PathStats(db)
        super().__init__()

    def on_mount(self) -> None:
        """Start auto-refresh timer when screen is mounted."""
        self.set_interval(10, self.action_refresh)

    def compose(self) -> ComposeResult:
        start_time = time.time()

        with Container(classes="path-stats-container"):
            with Vertical(classes="header-section"):
                yield Static(
                    f"{self.service.name}:{self.service.port} - Path stats | Step=1min | Refresh=10sec",
                    classes="title",
                )

                # Show information about ignored path stats if any are configured
                if self.service.ignore_path_stats:
                    ignored_parts = []
                    for ignored_path in self.service.ignore_path_stats:
                        ignored_parts.append(f"{ignored_path.method} {ignored_path.path}")
                    ignored_text = f"Ignored {', '.join(ignored_parts)}"
                    yield Static(ignored_text, classes="ignored-info")

            with VerticalScroll(classes="scrollable-content"):
                # Get all method+path combinations with time series data for this port
                path_time_data = self.path_stats.get_time_series_with_totals(self.port)

                generation_time = time.time() - start_time

                if not path_time_data:
                    yield Static("No recent path activity for this port", classes="path-label")
                    yield Static(f"Generated in {generation_time:.3f}s", classes="time-info")
                else:
                    yield Static(
                        f"Generated {len(path_time_data)} entries in {generation_time:.3f}s",
                        classes="time-info",
                    )

                    for (method, path), data in path_time_data.items():
                        total_count = data["total_count"]
                        time_series = data["time_series"]

                        with Horizontal(classes="path-line"):
                            yield Static(method, classes="method-label")
                            # Truncate path if too long
                            display_path = path if len(path) <= 45 else path[:42] + "..."
                            yield Static(display_path, classes="path-label")
                            yield Static(f"{total_count:,}", classes="count-label")
                            yield Sparkline(
                                time_series, summary_function=max, classes="sparkline-widget"
                            )

    def action_refresh(self) -> None:
        """Manual refresh action."""
        start_time = time.time()
        self.refresh(recompose=True)
        refresh_time = time.time() - start_time
        # Show refresh time temporarily in the title
        try:
            title_widget = self.query_one(".title", Static)
            original_text = title_widget.renderable
            title_widget.update(f"{original_text} | Refreshed in {refresh_time:.3f}s")
            # Reset after 3 seconds
            self.set_timer(3.0, lambda: title_widget.update(original_text))
        except Exception:
            # If we can't find the title widget, just skip the timing display
            pass

    def action_close(self) -> None:
        """Close the path stats screen."""
        self.app.pop_screen()
