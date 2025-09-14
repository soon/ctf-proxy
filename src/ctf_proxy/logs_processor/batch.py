import json
import logging
import os
import signal
import sys
import tarfile
import threading
from datetime import datetime, timedelta

from ctf_proxy.config.config import Config
from ctf_proxy.db.models import make_db

from .http import HttpAccessLogReader
from .tap_processor import TapProcessor

DEFAULT_TAP_FOLDER = "/var/log/envoy/taps"
DEFAULT_HTTP_ACCESS_LOG = "/var/log/envoy/http_access.log"
DEFAULT_DB_FILE = "proxy_stats.db"
DEFAULT_ARCHIVE_FOLDER = "/var/log/envoy/archive"
DEFAULT_CONFIG_FILE = "config.yaml"
DEFAULT_MAX_FILES_PER_BATCH = 100
DEFAULT_DURATION_MS = 100
SLEEP_WHEN_NO_FILES = 5
SLEEP_BETWEEN_BATCHES = 1
SLEEP_ON_ERROR = 5
IGNORED_TAP_TIMEOUT_SECONDS = 60

logger = logging.getLogger(__name__)


class BatchProcessor:
    def __init__(
        self,
        config: Config,
        tap_folder=DEFAULT_TAP_FOLDER,
        http_access_log=DEFAULT_HTTP_ACCESS_LOG,
        db_file=DEFAULT_DB_FILE,
        archive_folder=DEFAULT_ARCHIVE_FOLDER,
    ):
        self.tap_folder = tap_folder
        self.http_access_log = http_access_log
        self.db_file = db_file
        self.archive_folder = archive_folder
        self.running = True
        self.max_files_per_batch = DEFAULT_MAX_FILES_PER_BATCH
        self.shutdown_event = threading.Event()

        self.ignored_taps: dict[str, datetime] = {}
        self.next_batch_count = 1

        os.makedirs(self.archive_folder, exist_ok=True)
        self.db = make_db(self.db_file)
        self.config = config
        self.tap_processor = TapProcessor(self.db, config)
        self.http_access_log = HttpAccessLogReader(
            self.http_access_log, processed_position_file=f"{self.http_access_log}_position.txt"
        )
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame_):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
        self.shutdown_event.set()
        self.http_access_log.save_position()

    def wait_or_shutdown(self, duration):
        return self.shutdown_event.wait(timeout=duration)

    def get_tap_files(self):
        # todo rewrite with iterative walk
        if not os.path.exists(self.tap_folder):
            return []

        json_files = []
        for file in os.listdir(self.tap_folder):
            if file.endswith(".json"):
                json_files.append(os.path.join(self.tap_folder, file))

        json_files.sort(key=os.path.getctime)
        return json_files[: self.max_files_per_batch]

    def get_next_batch_unique_id(self):
        return self.db.get_next_batch_unique_id()

    def create_batch_id(self):
        datetime_str = datetime.now().isoformat()
        batch_id = f"batch_{datetime_str}_{self.next_batch_count}"
        self.next_batch_count += 1
        return batch_id

    def process_batch(self, batch_id: str, tap_files: list[str]):
        self.http_access_log.read_new_entries()

        processed_tap_files = []

        for tap_file in tap_files:
            tap_id = os.path.basename(tap_file).replace(".json", "")

            request_id = self.extract_request_id_from_tap(tap_file)
            log_entry = self.http_access_log.get_log_entry(request_id) if request_id else None
            if not log_entry:
                ignored_since = self.ignored_taps.get(tap_id, datetime.now())
                if datetime.now() - ignored_since > timedelta(seconds=IGNORED_TAP_TIMEOUT_SECONDS):
                    log_entry = {}
                    logger.debug(f"Timeout reached for tap {tap_id}, processing without log entry")
                else:
                    self.ignored_taps[tap_id] = ignored_since
                    logger.debug(f"Ignoring tap {tap_id}, no matching log entry yet")
                    continue

            self.tap_processor.process_tap_file(tap_file, tap_id, batch_id, log_entry)
            self.http_access_log.remove_log_entry(request_id)
            self.ignored_taps.pop(tap_id, None)
            processed_tap_files.append(tap_file)
            logger.debug(f"Processed {tap_id}")

        if processed_tap_files:
            archive_file = self.archive_batch(batch_id, processed_tap_files)

            for tap_file in processed_tap_files:
                os.remove(tap_file)

            logger.info(
                f"Processed batch {batch_id} -> {archive_file} ({len(self.ignored_taps)} ignored)"
            )

        return len(processed_tap_files)

    def extract_request_id_from_tap(self, tap_file_path: str) -> str | None:
        try:
            with open(tap_file_path) as f:
                data = json.load(f)

            http_trace = data.get("http_buffered_trace", {})
            request = http_trace.get("request", {})
            for header in request.get("headers", []):
                if header.get("key") == "x-request-id":
                    return header.get("value")

            response = http_trace.get("response", {})
            for header in response.get("headers", []):
                if header.get("key") == "x-request-id":
                    return header.get("value")
        except Exception as e:
            logger.error(f"Error extracting request ID from {tap_file_path}: {e}")

        return None

    def archive_batch(self, batch_id, tap_files):
        archive_file = os.path.join(self.archive_folder, f"{batch_id}.tar.gz")

        with tarfile.open(archive_file, "w:gz") as tar:
            for tap_file in tap_files:
                tar.add(tap_file, arcname=os.path.basename(tap_file))

        return archive_file

    def process_taps(self):
        while self.running:
            try:
                tap_files = self.get_tap_files()

                if not tap_files:
                    logger.debug(f"No tap files found in {self.tap_folder}, waiting...")
                    if self.wait_or_shutdown(SLEEP_WHEN_NO_FILES):
                        break
                    continue

                batch_id = self.create_batch_id()
                processed_count = self.process_batch(batch_id, tap_files)

                if processed_count > 0:
                    logger.info(f"Processed {processed_count} tap files in batch {batch_id}")

                if self.running:
                    if self.wait_or_shutdown(SLEEP_BETWEEN_BATCHES):
                        break

            except Exception:
                logger.exception("Unable to process taps")
                if self.wait_or_shutdown(SLEEP_ON_ERROR):
                    break

    def print_stats(self):
        stats = self.db.get_stats()

        logger.info("\n--- CTF Proxy Stats ---")
        logger.info(f"Total requests: {stats['total_requests']}")
        logger.info(f"Unique paths: {stats['unique_paths']}")
        logger.info(f"Top methods: {', '.join([f'{m}({c})' for m, c in stats['top_methods']])}")
        logger.info("Top paths:")
        for path, count in stats["top_paths"]:
            logger.info(f"  {path}: {count} hits")
        logger.info("--- End Stats ---\n")

    def run(self):
        logger.info("Starting post-processor...")
        logger.info(f"Tap folder: {self.tap_folder}")
        logger.info(f"HTTP access log: {self.http_access_log}")
        logger.info(f"Archive folder: {self.archive_folder}")
        logger.info(f"Database: {self.db_file}")

        try:
            self.process_taps()
        except KeyboardInterrupt:
            pass
        finally:
            self.http_access_log.save_position()
            logger.info("Post-processor stopped")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    tap_folder = os.environ.get("TAP_FOLDER", DEFAULT_TAP_FOLDER)
    http_access_log = os.environ.get("HTTP_ACCESS_LOG", DEFAULT_HTTP_ACCESS_LOG)
    db_file = os.environ.get("DB_FILE", DEFAULT_DB_FILE)
    archive_folder = os.environ.get("ARCHIVE_FOLDER", DEFAULT_ARCHIVE_FOLDER)
    config_file = os.environ.get("CONFIG_FILE", DEFAULT_CONFIG_FILE)

    if len(sys.argv) > 1:
        tap_folder = sys.argv[1]
    if len(sys.argv) > 2:
        http_access_log = sys.argv[2]
    if len(sys.argv) > 3:
        db_file = sys.argv[3]
    if len(sys.argv) > 4:
        archive_folder = sys.argv[4]
    if len(sys.argv) > 5:
        config_file = sys.argv[5]

    with Config(config_file) as config:
        config.start_watching()
        processor = BatchProcessor(config, tap_folder, http_access_log, db_file, archive_folder)
        processor.run()
