import threading
import time
from pathlib import Path


class Watcher:
    def __init__(self, watch_file, call_func_on_change=None, refresh_delay_secs=1, *args, **kwargs):
        self._cached_stamp = 0
        self.filename = Path(watch_file)
        self.call_func_on_change = call_func_on_change
        self.refresh_delay_secs = refresh_delay_secs
        self.args = args
        self.kwargs = kwargs
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def look(self):
        if not self.filename.exists():
            return

        stamp = self.filename.stat().st_mtime
        if stamp != self._cached_stamp:
            self._cached_stamp = stamp
            if self.call_func_on_change is not None:
                self.call_func_on_change(*self.args, **self.kwargs)

    def _watch_loop(self):
        while self._running:
            try:
                time.sleep(self.refresh_delay_secs)
                if self._running:
                    self.look()
            except KeyboardInterrupt:
                break
            except FileNotFoundError:
                pass
            except Exception:
                pass

    def start_watching(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._watch_loop, daemon=True)
            self._thread.start()

    def stop_watching(self):
        with self._lock:
            if not self._running:
                return
            self._running = False
            if self._thread and self._thread.is_alive():
                self._thread.join()
            self._thread = None

    def is_watching(self):
        with self._lock:
            return self._running and self._thread and self._thread.is_alive()

    def __enter__(self):
        self.start_watching()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_watching()
