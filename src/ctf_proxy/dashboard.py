#!/usr/bin/env python3

from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Label,
    Static,
    TabbedContent,
    TabPane,
)

from ctf_proxy.config import Config
from ctf_proxy.db import ProxyStatsDB


class ServiceMetrics:
    def __init__(self, service_name: str, db: ProxyStatsDB):
        self.service_name = service_name
        self.db = db

    def get_request_count(self) -> int:
        with self.db.requests.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT COUNT(*) FROM requests WHERE upstream_host LIKE ?""",
                (f"%{self.service_name}%",),
            )
            result = cursor.fetchone()
            return result[0] if result else 0

    def get_error_rate(self) -> float:
        with self.db.requests.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) as errors
                FROM requests
                WHERE upstream_host LIKE ?
            """,
                (f"%{self.service_name}%",),
            )
            result = cursor.fetchone()
            if not result or result[0] == 0:
                return 0.0
            return (result[1] / result[0]) * 100

    def get_avg_response_time(self) -> float:
        with self.db.requests.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT AVG(duration_ms) FROM requests
                WHERE upstream_host LIKE ?
            """,
                (f"%{self.service_name}%",),
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else 0.0

    def get_recent_requests(self, limit: int = 10) -> list[tuple]:
        with self.db.requests.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT timestamp, method, path, status, duration_ms, bytes_in, bytes_out
                FROM requests
                WHERE upstream_host LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (f"%{self.service_name}%", limit),
            )
            return cursor.fetchall()

    def get_status_distribution(self) -> list[tuple]:
        with self.db.requests.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT status, COUNT(*) as count
                FROM requests
                WHERE upstream_host LIKE ?
                GROUP BY status
                ORDER BY count DESC
            """,
                (f"%{self.service_name}%",),
            )
            return cursor.fetchall()


class ServiceOverviewWidget(Static):
    def __init__(self, service_name: str, port: int, service_type: str, metrics: ServiceMetrics):
        self.service_name = service_name
        self.port = port
        self.service_type = service_type
        self.metrics = metrics
        super().__init__()

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(
                f"[bold]{self.service_name}[/bold] ({self.service_type.upper()})",
                classes="service-title",
            )
            yield Label(f"Port: {self.port}")

            with Horizontal():
                with Vertical():
                    yield Label("[bold]Total Requests[/bold]")
                    yield Label(
                        str(self.metrics.get_request_count()), id=f"requests-{self.service_name}"
                    )

                with Vertical():
                    yield Label("[bold]Error Rate[/bold]")
                    error_rate = self.metrics.get_error_rate()
                    color = "red" if error_rate > 5 else "yellow" if error_rate > 1 else "green"
                    yield Label(
                        f"[{color}]{error_rate:.1f}%[/{color}]",
                        id=f"error-rate-{self.service_name}",
                    )

                with Vertical():
                    yield Label("[bold]Avg Response Time[/bold]")
                    avg_time = self.metrics.get_avg_response_time()
                    yield Label(f"{avg_time:.0f}ms", id=f"avg-time-{self.service_name}")


class ServiceDetailWidget(ScrollableContainer):
    def __init__(self, service_name: str, metrics: ServiceMetrics):
        self.service_name = service_name
        self.metrics = metrics
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Label(f"[bold]{self.service_name} - Recent Activity[/bold]")

        recent_table = DataTable(id=f"recent-{self.service_name}")
        recent_table.add_columns("Time", "Method", "Path", "Status", "Duration", "In", "Out")

        for req in self.metrics.get_recent_requests():
            timestamp, method, path, status, duration, bytes_in, bytes_out = req
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M:%S")
            except Exception:
                time_str = timestamp[:8] if len(timestamp) >= 8 else timestamp

            status_color = "red" if status >= 400 else "yellow" if status >= 300 else "green"
            recent_table.add_row(
                time_str,
                method,
                path[:30] + "..." if len(path) > 30 else path,
                f"[{status_color}]{status}[/{status_color}]",
                f"{duration}ms",
                f"{bytes_in}B",
                f"{bytes_out}B",
            )

        yield recent_table

        yield Label("\n[bold]Status Code Distribution[/bold]")
        status_table = DataTable(id=f"status-{self.service_name}")
        status_table.add_columns("Status Code", "Count", "Percentage")

        status_dist = self.metrics.get_status_distribution()
        total_requests = sum(count for _, count in status_dist)

        for status, count in status_dist:
            percentage = (count / total_requests * 100) if total_requests > 0 else 0
            status_color = "red" if status >= 400 else "yellow" if status >= 300 else "green"
            status_table.add_row(
                f"[{status_color}]{status}[/{status_color}]", str(count), f"{percentage:.1f}%"
            )

        yield status_table


class CTFProxyDashboard(App):
    CSS = """
    .service-title {
        text-style: bold;
        margin-bottom: 1;
    }

    #services-overview {
        height: 50%;
        border: solid $primary;
        margin: 1;
    }

    .service-card {
        border: solid $secondary;
        margin: 1;
        padding: 1;
        height: auto;
    }

    DataTable {
        margin: 1 0;
    }
    """

    def __init__(self, config_path: str, db_path: str):
        self.config = Config(config_path)
        self.db = ProxyStatsDB(db_path)
        self.metrics = {
            service.name: ServiceMetrics(service.name, self.db) for service in self.config.services
        }
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()

        with TabbedContent(initial="overview"):
            with TabPane("Services Overview", id="overview"):
                with ScrollableContainer(id="services-overview"):
                    for service in self.config.services:
                        with Container(classes="service-card"):
                            yield ServiceOverviewWidget(
                                service.name,
                                service.port,
                                service.type.value,
                                self.metrics[service.name],
                            )

            for service in self.config.services:
                with TabPane(f"{service.name}", id=f"tab-{service.name}"):
                    yield ServiceDetailWidget(service.name, self.metrics[service.name])

            with TabPane("System Stats", id="system"):
                yield Label("[bold]Database Statistics[/bold]")

                db_table = DataTable(id="db-stats")
                db_table.add_columns("Table", "Records")

                db_table.add_row("Total Requests", str(self.db.requests.get_count()))
                db_table.add_row("Unique Paths", str(self.db.requests.get_unique_paths_count()))
                db_table.add_row("Batches Processed", str(self.db.batches.get_count()))

                yield db_table

                yield Label("\n[bold]Top Paths by Traffic[/bold]")
                top_paths_table = DataTable(id="top-paths")
                top_paths_table.add_columns("Path", "Hits", "Avg Time", "Error Rate")

                top_paths = self.db.path_stats.get_top_paths(10)
                for path_data in top_paths:
                    path, hits, avg_time, _, _, _, _, status_4xx, status_5xx, _ = path_data
                    error_count = status_4xx + status_5xx
                    error_rate = (error_count / hits * 100) if hits > 0 else 0

                    top_paths_table.add_row(
                        path[:40] + "..." if len(path) > 40 else path,
                        str(hits),
                        f"{avg_time:.0f}ms",
                        f"{error_rate:.1f}%",
                    )

                yield top_paths_table

        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(5.0, self.refresh_data)

    def refresh_data(self) -> None:
        for service_name in self.metrics:
            self.metrics[service_name] = ServiceMetrics(service_name, self.db)

        for service in self.config.services:
            try:
                requests_widget = self.query_one(f"#requests-{service.name}", Label)
                requests_widget.update(str(self.metrics[service.name].get_request_count()))
            except Exception:
                pass

            try:
                error_rate_widget = self.query_one(f"#error-rate-{service.name}", Label)
                error_rate = self.metrics[service.name].get_error_rate()
                color = "red" if error_rate > 5 else "yellow" if error_rate > 1 else "green"
                error_rate_widget.update(f"[{color}]{error_rate:.1f}%[/{color}]")
            except Exception:
                pass

            try:
                avg_time_widget = self.query_one(f"#avg-time-{service.name}", Label)
                avg_time = self.metrics[service.name].get_avg_response_time()
                avg_time_widget.update(f"{avg_time:.0f}ms")
            except Exception:
                pass


def main():
    import argparse

    parser = argparse.ArgumentParser(description="CTF Proxy Dashboard")
    parser.add_argument(
        "--config", default="config.yml", help="Path to configuration file (default: config.yml)"
    )
    parser.add_argument(
        "--db",
        default="data/proxy_stats.db",
        help="Path to database file (default: data/proxy_stats.db)",
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

    app = CTFProxyDashboard(str(config_path), str(db_path))
    app.run()


if __name__ == "__main__":
    exit(main())
