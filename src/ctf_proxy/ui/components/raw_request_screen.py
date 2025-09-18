import os
import tarfile

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Label, Static

from ctf_proxy.db.models import ProxyStatsDB


class RawRequestScreen(Screen):
    DEFAULT_CSS = """
      RawRequestScreen {
        align: center middle;
      }

      .raw-container {
        background: $surface;
        border: thick $primary;
        width: 95%;
        height: 95%;
        padding: 1;
      }

      .raw-header {
        height: 3;
        margin-bottom: 1;
      }

      .raw-content {
        height: 1fr;
        border: solid $accent;
        padding: 1;
      }

      .scrollable-json {
        height: 1fr;
        scrollbar-gutter: stable;
      }

      .error-message {
        color: $error;
        text-align: center;
        height: 1fr;
      }
    """

    BINDINGS = [
        ("escape", "dismiss", "Back"),
        ("q", "dismiss", "Quit"),
    ]

    def __init__(
        self, request_id: int, db: ProxyStatsDB, archive_folder: str = "/var/log/envoy/archive"
    ):
        self.request_id = request_id
        self.db = db
        self.archive_folder = archive_folder
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical(classes="raw-container"):
            yield Static(
                f"Raw Request Data - Request ID: {self.request_id} - Press ESC to go back",
                classes="raw-header",
                id="header-info",
            )
            with Vertical(classes="raw-content"):
                yield Label("Raw JSON:", id="content-label")
                with ScrollableContainer(classes="scrollable-json"):
                    yield Static("Loading...", id="json-content", markup=False)

    def on_mount(self) -> None:
        self._load_raw_data()

    def _load_raw_data(self) -> None:
        raw_json = self._fetch_raw_json_for_request(self.request_id)
        if raw_json:
            content_widget = self.query_one("#json-content")
            content_widget.update(raw_json)
        else:
            self._show_error("No raw data found for this request")

        # try:
        #     raw_json = self._fetch_raw_json_for_request(self.request_id)
        #     if raw_json:
        #         content_widget = self.query_one("#json-content")
        #         content_widget.update(raw_json)
        #     else:
        #         self._show_error("No raw data found for this request")
        # except Exception as e:
        #     self._show_error(f"Error loading raw data: {str(e)}")

    def _show_error(self, message: str) -> None:
        content_widget = self.query_one("#json-content")
        content_widget.add_class("error-message")
        content_widget.update(message)

    def _fetch_raw_json_for_request(self, request_id: int) -> str | None:
        """
        Fetch raw JSON for a request by:
        1. Getting batch_id and tap_id from database
        2. Finding the archive file for that batch
        3. Extracting the JSON file from the archive
        """
        # Get batch_id and tap_id for the request
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT batch_id, tap_id FROM http_request WHERE id = ?", (request_id,))
            result = cursor.fetchone()

            if not result:
                return None

            batch_id, tap_id = result

            if not batch_id or not tap_id:
                return None

        # Construct archive file path from batch_id (since batches table may not exist)
        archive_file = os.path.join(self.archive_folder, f"{batch_id}.tar.gz")

        # Check if archive file exists
        if not os.path.exists(archive_file):
            raise FileNotFoundError(f"Archive file not found: {archive_file}")

        # Extract and read the JSON file from the archive
        tap_filename = f"{tap_id}.json"

        try:
            with tarfile.open(archive_file, "r:gz") as tar:
                # Try to extract the specific file
                try:
                    member = tar.getmember(tap_filename)
                    extracted_file = tar.extractfile(member)
                    if extracted_file:
                        json_content = extracted_file.read().decode("utf-8")
                        return json_content
                except KeyError:
                    # File not found in archive, list all files for debugging
                    available_files = tar.getnames()
                    raise FileNotFoundError(
                        f"File {tap_filename} not found in archive. "
                        f"Available files: {', '.join(available_files[:10])}{'...' if len(available_files) > 10 else ''}"
                    ) from None
        except Exception as e:
            raise Exception(f"Error reading archive {archive_file}: {str(e)}") from e

        return None

    def action_dismiss(self) -> None:
        self.dismiss()
