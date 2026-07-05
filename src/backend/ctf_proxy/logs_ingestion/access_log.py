import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AccessLogEntry:
    data: dict
    end_position: int


class AccessLogReader:
    def __init__(self, path: str):
        self.path = path
        self.last_position = self.read_last_processed_position()

    def read_last_processed_position(self) -> int:
        try:
            with open(self.path + ".pos") as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def read_new_entries(self, max_entries=None) -> list[AccessLogEntry]:
        new_entries: list[AccessLogEntry] = []
        with open(self.path) as f:
            f.seek(self.last_position)
            while line := f.readline():
                line = line.strip()
                if not line:
                    continue
                try:
                    log_entry = json.loads(line)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse log line as JSON: {line}")
                    continue

                self.last_position = f.tell()
                new_entries.append(AccessLogEntry(data=log_entry, end_position=self.last_position))
                if max_entries is not None and len(new_entries) >= max_entries:
                    break

        return new_entries

    def write_last_processed_position(self, position: int) -> None:
        with open(self.path + ".pos", "w") as f:
            f.write(str(position))
