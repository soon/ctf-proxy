import json
import logging
import os
import shutil

logger = logging.getLogger(__name__)


class TapsFolder:
    max_load_retries = 3

    def __init__(self, path: str):
        self.path = path
        self.indexed = set()
        self.to_remove = set()
        self.dirs_to_remove = set()
        self.failed_to_load = {}

    def refresh(self):
        with os.scandir(self.path) as it:
            for entry in it:
                if entry.name in self.indexed or entry.name in self.to_remove:
                    continue

                if entry.is_file(follow_symlinks=False):
                    if entry.name.endswith(".json"):
                        self.try_index_file(entry.name)
                    else:
                        self.to_remove.add(entry.name)

    def try_index_file(self, filename: str):
        data = self.load_file(filename)
        if data is None:
            return
        self.indexed.add(filename)
        self.on_file_loaded(filename, data)

    def load_file(self, filename: str) -> dict | None:
        file_path = os.path.join(self.path, filename)
        try:
            with open(file_path) as f:
                return json.load(f)
        except Exception as e:
            if filename not in self.failed_to_load:
                logger.error(f"Error loading tap file {file_path}: {e}")
                self.failed_to_load[filename] = 0
            self.failed_to_load[filename] += 1
            if self.failed_to_load[filename] >= self.max_load_retries:
                logger.error(
                    f"Giving up on loading tap file {file_path} after {self.max_load_retries} attempts"
                )
                self.to_remove.add(filename)
            return None

    def on_file_loaded(self, filename: str, data: dict):
        pass

    def pop_filename(self, filename: str) -> dict | None:
        data = self.load_file(filename)
        if data is not None:
            self.to_remove.add(filename)
        return data

    def cleanup(self):
        for filename in self.to_remove:
            file_path = os.path.join(self.path, filename)
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Error removing tap file {file_path}: {e}")
            self.indexed.discard(filename)
            self.failed_to_load.pop(filename, None)
        self.to_remove.clear()

        for dir_name in self.dirs_to_remove:
            dir_path = os.path.join(self.path, dir_name)
            try:
                shutil.rmtree(dir_path)
            except Exception as e:
                logger.error(f"Error removing tap directory {dir_path}: {e}")
        self.dirs_to_remove.clear()
