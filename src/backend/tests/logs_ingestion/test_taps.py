import json

from ctf_proxy.logs_ingestion.http import HttpTapsFolder


def write_tap(folder, filename: str, request_id: str):
    tap = {
        "http_buffered_trace": {
            "request": {
                "headers": [
                    {"key": "x-request-id", "value": request_id},
                    {"key": ":path", "value": "/"},
                ]
            },
            "response": {"headers": []},
        }
    }
    (folder / filename).write_text(json.dumps(tap))


def test_refresh_indexes_without_holding_payloads(tmp_path):
    write_tap(tmp_path, "http__1.json", "req-1")
    write_tap(tmp_path, "http__2.json", "req-2")

    folder = HttpTapsFolder(str(tmp_path))
    folder.refresh()

    assert folder.request_id_to_file == {"req-1": "http__1.json", "req-2": "http__2.json"}
    assert folder.indexed == {"http__1.json", "http__2.json"}
    assert not hasattr(folder, "cache")


def test_pop_filename_loads_lazily_from_disk(tmp_path):
    write_tap(tmp_path, "http__1.json", "req-1")

    folder = HttpTapsFolder(str(tmp_path))
    folder.refresh()

    filename = folder.pop_tap_filename_by_request_id("req-1")
    assert filename == "http__1.json"

    data = folder.pop_filename(filename)
    assert data["http_buffered_trace"]["request"]["headers"][0]["value"] == "req-1"


def test_refresh_skips_already_indexed_files(tmp_path):
    write_tap(tmp_path, "http__1.json", "req-1")

    folder = HttpTapsFolder(str(tmp_path))
    folder.refresh()

    loaded = []
    original = folder.load_file
    folder.load_file = lambda name: loaded.append(name) or original(name)
    folder.refresh()

    assert loaded == []


def test_cleanup_removes_files_and_clears_index(tmp_path):
    write_tap(tmp_path, "http__1.json", "req-1")

    folder = HttpTapsFolder(str(tmp_path))
    folder.refresh()
    folder.pop_filename("http__1.json")
    folder.cleanup()

    assert not (tmp_path / "http__1.json").exists()
    assert folder.indexed == set()
