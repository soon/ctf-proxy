import io
import json
import logging
import os
import signal
import sys
import tarfile
import threading
from datetime import datetime

from ctf_proxy.config.config import Config
from ctf_proxy.db.models import make_db

from .http import HttpProcessor
from .tcp import TcpProcessor

DEFAULT_HTTP_TAP_FOLDER = "/app/logs/tap"
DEFAULT_HTTP_ACCESS_LOG = "/app/logs/http_access.log"
DEFAULT_TCP_ACCESS_LOG = "/app/logs/tcp_access.log"
DEFAULT_TCP_TAP_FOLDER = "/app/logs/tcp-tap"
DEFAULT_DB_FILE = "/app/data/proxy_stats.db"
DEFAULT_ARCHIVE_FOLDER = "/app/logs-archive"
DEFAULT_CONFIG_FILE = "/app/data/config.yml"
SLEEP_WHEN_NO_FILES = 5
SLEEP_BETWEEN_BATCHES = 1
SLEEP_ON_ERROR = 5

logger = logging.getLogger(__name__)


class BatchProcessor:
    def __init__(
        self,
        config: Config,
        http_tap_folder=DEFAULT_HTTP_TAP_FOLDER,
        http_access_log=DEFAULT_HTTP_ACCESS_LOG,
        tcp_access_log=DEFAULT_TCP_ACCESS_LOG,
        tcp_tap_folder=DEFAULT_TCP_TAP_FOLDER,
        db_file=DEFAULT_DB_FILE,
        archive_folder=DEFAULT_ARCHIVE_FOLDER,
    ):
        self.http_tap_folder = http_tap_folder
        self.http_access_log_path = http_access_log
        self.tcp_access_log_path = tcp_access_log
        self.tcp_tap_folder = tcp_tap_folder
        self.db_file = db_file
        self.archive_folder = archive_folder
        self.running = True
        self.shutdown_event = threading.Event()
        self.next_batch_count = 1

        os.makedirs(self.archive_folder, exist_ok=True)
        self.db = make_db(self.db_file)
        self.config = config

        # Initialize the new processors
        self.http_processor = HttpProcessor(
            db=self.db,
            config=config,
            access_log_path=self.http_access_log_path,
            taps_dir=self.http_tap_folder,
        )

        self.tcp_processor = TcpProcessor(
            db=self.db,
            config=config,
            access_log_path=self.tcp_access_log_path,
            taps_dir=self.tcp_tap_folder,
        )

        self.processors = [self.http_processor, self.tcp_processor]

        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame_):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
        self.shutdown_event.set()

    def wait_or_shutdown(self, duration):
        return self.shutdown_event.wait(timeout=duration)

    def create_batch_id(self):
        datetime_str = datetime.now().isoformat()
        batch_id = f"batch_{datetime_str}_{self.next_batch_count}"
        self.next_batch_count += 1
        return batch_id

    def process_batch(self):
        total_processed = 0
        for processor in self.processors:
            try:
                batch_id = self.create_batch_id()
                processed = processor.process_new_access_log_entries(batch_id)
                total_processed += len(processed)
                self.save_archive(batch_id, processed)
            except Exception as e:
                logger.error(f"Error processing entries by {processor.__class__.__name__}: {e}")

        return total_processed

    def save_archive(self, batch_id: str, to_archive: dict[str, dict]):
        if not to_archive:
            return

        archive_path = os.path.join(self.archive_folder, f"{batch_id}.tar.gz")

        with tarfile.open(archive_path, "w:gz") as tar:
            for name, data in to_archive.items():
                try:
                    json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
                    info = tarfile.TarInfo(name)
                    info.size = len(json_bytes)
                    tar.addfile(info, io.BytesIO(json_bytes))
                except Exception as e:
                    logger.error(f"Failed to archive {name}: {e}")

        logger.info(f"Saved archive {archive_path} with {len(to_archive)} items")

    def process_taps(self):
        while self.running:
            logger.info("Checking for new log entries...")
            try:
                start = datetime.now()
                processed_count = self.process_batch()
                duration = (datetime.now() - start).total_seconds() * 1000

                if processed_count > 0:
                    logger.info(f"Processed batch in {duration:.2f} ms")

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
        logger.info(f"HTTP tap folder: {self.http_tap_folder}")
        logger.info(f"TCP tap folder: {self.tcp_tap_folder}")
        logger.info(f"HTTP access log: {self.http_access_log_path}")
        logger.info(f"TCP access log: {self.tcp_access_log_path}")
        logger.info(f"Archive folder: {self.archive_folder}")
        logger.info(f"Database: {self.db_file}")

        try:
            self.process_taps()
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("Post-processor stopped")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    http_tap_folder = os.environ.get("HTTP_TAP_FOLDER", DEFAULT_HTTP_TAP_FOLDER)
    http_access_log = os.environ.get("HTTP_ACCESS_LOG", DEFAULT_HTTP_ACCESS_LOG)
    tcp_access_log = os.environ.get("TCP_ACCESS_LOG", DEFAULT_TCP_ACCESS_LOG)
    tcp_tap_folder = os.environ.get("TCP_TAP_FOLDER", DEFAULT_TCP_TAP_FOLDER)
    db_file = os.environ.get("DB_FILE", DEFAULT_DB_FILE)
    archive_folder = os.environ.get("ARCHIVE_FOLDER", DEFAULT_ARCHIVE_FOLDER)
    config_file = os.environ.get("CONFIG_FILE", DEFAULT_CONFIG_FILE)

    # Support legacy command line arguments
    if len(sys.argv) > 1:
        http_tap_folder = sys.argv[1]
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
        processor = BatchProcessor(
            config,
            http_tap_folder,
            http_access_log,
            tcp_access_log,
            tcp_tap_folder,
            db_file,
            archive_folder,
        )
        processor.run()
