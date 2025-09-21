import json
import logging
import os
import shutil

logger = logging.getLogger(__name__)


class TapsFolder:
    max_load_retries = 3

    def __init__(self, path: str):
        self.path = path
        self.cache = {}
        self.to_remove = set()
        self.dirs_to_remove = set()
        self.failed_to_load = {}

    def refresh(self):
        with os.scandir(self.path) as it:
            for entry in it:
                if entry.name in self.cache or entry.name in self.to_remove:
                    continue

                if entry.is_file(follow_symlinks=False):
                    if entry.name.endswith(".json"):
                        self.try_load_file(entry.name)
                    else:
                        self.to_remove.add(entry.name)

    def try_load_file(self, filename: str):
        file_path = os.path.join(self.path, filename)
        try:
            with open(file_path) as f:
                data = json.load(f)
                self.cache[filename] = data
                self.on_file_loaded(filename, data)
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

    def on_file_loaded(self, filename: str, data: dict):
        pass

    def pop_filename(self, filename: str) -> dict | None:
        data = self.cache.pop(filename, None)
        if data:
            self.to_remove.add(filename)
        return data

    def cleanup(self):
        for filename in self.to_remove:
            file_path = os.path.join(self.path, filename)
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Error removing tap file {file_path}: {e}")
            self.cache.pop(filename, None)
            self.failed_to_load.pop(filename, None)
        self.to_remove.clear()

        for dir_name in self.dirs_to_remove:
            dir_path = os.path.join(self.path, dir_name)
            try:
                shutil.rmtree(dir_path)
            except Exception as e:
                logger.error(f"Error removing tap directory {dir_path}: {e}")
        self.dirs_to_remove.clear()
