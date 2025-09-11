#!/usr/bin/env python3

import os
import tempfile

from ctf_proxy.db import ProxyStatsDB


def test_db_operations():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_file = f.name

    try:
        db = ProxyStatsDB(db_file)

        tap_files = ["/tmp/test1.json", "/tmp/test2.json"]
        batch_id = db.create_batch(tap_files)
        print(f"Created batch: {batch_id}")

        db.insert_request(
            "test_tap_1",
            batch_id,
            "2024-01-01T12:00:00",
            "GET",
            "/api/test",
            200,
            100,
            1024,
            2048,
            "localhost:8080",
            "/api/test",
            None,
        )

        db.update_path_stats("/api/test", 100, 1024, 2048, 200)
        db.update_method_stats("GET")
        db.update_status_stats(200)

        stats = db.get_stats()
        print(f"Stats: {stats}")

        print("All DB operations completed successfully!")

    finally:
        os.unlink(db_file)


if __name__ == "__main__":
    test_db_operations()
