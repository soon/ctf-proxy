import time

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Sparkline, Static

from ctf_proxy.config import Service
from ctf_proxy.db import ProxyStatsDB


class BaseStatsScreen(Screen):
    stats_type_name: str = None
    DEFAULT_CSS = """
      BaseStatsScreen {
        align: center middle;
      }

      .stats-container {
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

      .stats-line {
        layout: horizontal;
        height: 1;
        margin: 0;
      }

      .key-label {
        width: 20;
        color: $accent;
        text-style: bold;
      }

      .value-label {
        width: 35;
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

      .time-info {
        text-align: center;
        color: $secondary;
        margin-bottom: 1;
        text-style: italic;
      }

      .ignored-info {
        text-align: center;
        color: $warning;
        text-style: italic;
        margin-bottom: 1;
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
        super().__init__()

    def get_stats_instance(self):
        """Return the stats instance for this screen"""
        raise NotImplementedError("Subclasses must implement get_stats_instance")

    def get_ignored_config(self) -> dict[str, str]:
        """Return the ignored configuration for this stats type"""
        raise NotImplementedError("Subclasses must implement get_ignored_config")

    def format_key_display(self, key: tuple) -> tuple[str, str]:
        """Format the key tuple for display, return (first_column, second_column)"""
        raise NotImplementedError("Subclasses must implement format_key_display")

    def on_mount(self) -> None:
        """Start auto-refresh timer when screen is mounted."""
        self.set_interval(10, self.action_refresh)

    def compose(self) -> ComposeResult:
        start_time = time.time()

        with Container(classes="stats-container"):
            with Vertical(classes="header-section"):
                yield Static(
                    f"{self.service.name}:{self.service.port} - {self.stats_type_name} | Step=1min | Refresh=10sec",
                    classes="title",
                )

                # Show information about ignored items if any are configured
                ignored_config = self.get_ignored_config()
                if ignored_config:
                    ignored_parts = []
                    for key, regex in ignored_config.items():
                        ignored_parts.append(f"{key} ~= {regex}")
                    ignored_text = f"Ignored {', '.join(ignored_parts)}"
                    yield Static(ignored_text, classes="ignored-info")

            with VerticalScroll(classes="scrollable-content"):
                # Get all key combinations with time series data for this port
                stats_data = self.get_stats_instance().get_time_series_with_totals(self.port)

                generation_time = time.time() - start_time

                if not stats_data:
                    yield Static(
                        f"No recent {self.stats_type_name.lower()} activity for this port",
                        classes="key-label",
                    )
                    yield Static(f"Generated in {generation_time:.3f}s", classes="time-info")
                else:
                    yield Static(
                        f"Generated {len(stats_data)} entries in {generation_time:.3f}s",
                        classes="time-info",
                    )

                    for key, data in stats_data.items():
                        total_count = data["total_count"]
                        time_series = data["time_series"]

                        with Horizontal(classes="stats-line"):
                            # Format key for display
                            first_col, second_col = self.format_key_display(key)

                            # Truncate if too long
                            display_first = (
                                first_col if len(first_col) <= 18 else first_col[:15] + "..."
                            )
                            display_second = (
                                second_col if len(second_col) <= 33 else second_col[:30] + "..."
                            )

                            yield Static(display_first, classes="key-label")
                            yield Static(display_second, classes="value-label")
                            yield Static(f"{total_count:,}", classes="count-label")
                            yield Sparkline(
                                time_series, summary_function=max, classes="sparkline-widget"
                            )

    def action_refresh(self) -> None:
        """Manual refresh action."""
        start_time = time.time()
        self.refresh(recompose=True)
        refresh_time = time.time() - start_time
        # Update the title to show refresh time temporarily
        self.call_after_refresh(lambda: self.show_refresh_time(refresh_time))

    def show_refresh_time(self, refresh_time: float) -> None:
        """Show refresh time temporarily in the title"""
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
        """Close the stats screen."""
        self.app.pop_screen()
