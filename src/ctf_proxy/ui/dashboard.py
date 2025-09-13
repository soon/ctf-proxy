#!/usr/bin/env python3

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Footer, Header, Input

from ctf_proxy.config import Config
from ctf_proxy.db import ProxyStatsDB
from ctf_proxy.ui.components import (
    RequestDetailScreen,
    ServiceBlock,
    ServiceDetailScreen,
    ServiceStats,
)


class Dashboard(Widget):
    DEFAULT_CSS = """
      Dashboard {
        layout: vertical;
      }

      .services-grid {
        layout: grid;
        grid-size: 3;
        height: 1fr;
      }

      .command-input {
        height: 3;
        dock: bottom;
        border: solid $primary;
        margin-top: 1;
      }
    """

    def __init__(self, config: Config, db: ProxyStatsDB):
        self.config = config
        self.db = db
        self.service_blocks = []
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical():
            with Widget(classes="services-grid"):
                for service in self.config.services:
                    stats = ServiceStats(service.port, self.db)
                    block = ServiceBlock(service.name, service.port, service.type.value, stats)
                    self.service_blocks.append(block)
                    yield block

            yield Input(
                placeholder="Enter command (e.g., s 3000 for service, r 123 for request, h for help)",
                classes="command-input",
                id="command-input",
            )

    def on_mount(self) -> None:
        self.set_interval(5.0, self.refresh_data)

    def refresh_data(self) -> None:
        for block in self.service_blocks:
            block.update_content()

    def on_service_block_clicked(self, message: ServiceBlock.Clicked) -> None:
        service = self.config.get_service_by_port(message.service_port)
        if service:
            self.app.push_screen(ServiceDetailScreen(service, self.db))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value.strip()
        input_widget = event.input

        if command.startswith("/s ") or command.startswith("s "):
            try:
                port_str = command[3:].strip() if command.startswith("/s ") else command[2:].strip()
                port = int(port_str)
                service = self.config.get_service_by_port(port)
                if service:
                    input_widget.value = ""
                    self.app.push_screen(ServiceDetailScreen(service, self.db))
                else:
                    input_widget.value = f"Error: No service found on port {port}"
            except ValueError:
                input_widget.value = "Error: Invalid port number"
        elif command.startswith("/r ") or command.startswith("r "):
            try:
                req_id_str = (
                    command[3:].strip() if command.startswith("/r ") else command[2:].strip()
                )
                req_id = int(req_id_str)
                input_widget.value = ""
                self.app.push_screen(RequestDetailScreen(req_id, self.db))
            except ValueError:
                input_widget.value = "Error: Invalid request ID"
        elif command.startswith("/h") or command == "/" or command == "h":
            available_commands = [
                "s <port> - Open service detail page",
                "/s <port> - Open service detail page",
                "r <req_id> - Open request detail page",
                "/r <req_id> - Open request detail page",
                "h - Show this help",
                "ESC - Clear command input",
            ]
            input_widget.value = f"Commands: {' | '.join(available_commands)}"
        else:
            input_widget.value = "Unknown command. Type h for help"

        if command and not (
            command.startswith("/s ")
            or command.startswith("s ")
            or command.startswith("/r ")
            or command.startswith("r ")
        ):
            self.set_timer(3.0, lambda: setattr(input_widget, "value", ""))


class CTFProxyDashboard(App):
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("q", "quit", "Quit"),
        ("/", "focus_command", "Focus Command Input"),
        ("escape", "clear_command", "Clear Command"),
    ]

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

    def action_focus_command(self) -> None:
        """Focus the command input"""
        command_input = self.query_one("#command-input", Input)
        command_input.focus()

    def action_clear_command(self) -> None:
        """Clear the command input"""
        command_input = self.query_one("#command-input", Input)
        command_input.value = ""
        command_input.focus()


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
