import json
import logging
import os

logger = logging.getLogger(__name__)


class HttpAccessLogReader:
    def __init__(self, http_access_log: str, processed_position_file: str = "logs_position.txt"):
        self.http_access_log = http_access_log
        self.processed_position_file = processed_position_file
        self.log_position = 0
        self.stream_id_to_log: dict[str, dict] = {}

        # self.load_log_position()

    def load_log_position(self):
        try:
            if os.path.exists(self.processed_position_file):
                with open(self.processed_position_file) as f:
                    self.log_position = int(f.read().strip())
                logger.info(f"Loaded log position: {self.log_position}")
            else:
                self.log_position = 0
        except Exception as e:
            logger.error(f"Error loading log position: {e}")
            self.log_position = 0

    def save_log_position(self):
        try:
            with open(self.processed_position_file, "w") as f:
                f.write(str(self.log_position))
        except Exception as e:
            logger.error(f"Error saving log position: {e}")

    def read_new_entries(self):
        if not os.path.exists(self.http_access_log):
            logger.debug(f"HTTP access log not found: {self.http_access_log}")
            return

        try:
            with open(self.http_access_log) as f:
                f.seek(self.log_position)

                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        log_entry = json.loads(line)
                        stream_id = log_entry.get("stream_id")
                        if stream_id:
                            self.stream_id_to_log[stream_id] = log_entry
                            logger.debug(f"Added log entry for stream_id: {stream_id}")
                    except json.JSONDecodeError as e:
                        logger.error(f"Error parsing log line: {line}, error: {e}")
                        continue

                self.log_position = f.tell()
                self.save_log_position()

        except Exception as e:
            logger.error(f"Error reading HTTP access log: {e}")

    def get_log_entry(self, stream_id: str) -> dict:
        return self.stream_id_to_log.get(stream_id)

    def remove_log_entry(self, stream_id: str):
        self.stream_id_to_log.pop(stream_id, None)

    def save_position(self):
        self.save_log_position()
