import json

from ctf_proxy.common.config import Config
from ctf_proxy.db.models import ProxyStatsDB
from ctf_proxy.db.utils import parse_headers
from ctf_proxy.logs_ingestion.batch_stats import BatchStats
from ctf_proxy.logs_ingestion.batch_writer import Batch
from ctf_proxy.logs_ingestion.http import (
    HttpTapHeaders,
    HttpTapProcessor,
    PathStatsAggregator,
    serialize_headers,
)
from tests.utils import assert_table


def test_headers_serialize_parse_roundtrip():
    headers = HttpTapHeaders(
        [
            {"key": "Host", "value": "example.com"},
            {"key": "X-Dup", "value": "a"},
            {"key": "X-Dup", "value": "b"},
        ]
    )
    # lowercased names, duplicates + order preserved
    assert parse_headers(serialize_headers(headers)) == [
        ("host", "example.com"),
        ("x-dup", "a"),
        ("x-dup", "b"),
    ]
    assert parse_headers(None) == []


def process_tap(db: ProxyStatsDB, file_path: str, tap_id="test-id", batch_id="test-batch"):
    with open(file_path) as f:
        data = json.load(f)

    log_entry = data["log-entry"]
    tap = data["tap"]

    config = Config("tests/logs_ingestion/data/test-config.yaml")
    processor = HttpTapProcessor(db=db, config=config)
    with db.connect() as conn:
        tx = conn.cursor()
        writer = Batch()
        stats = BatchStats()
        paths = PathStatsAggregator()
        processor.process_tap(
            tap,
            tap_id=tap_id,
            batch_id=batch_id,
            log_entry=log_entry,
            writer=writer,
            stats=stats,
            paths=paths,
        )
        writer.flush(tx)
        paths.flush(tx)
        stats.flush(tx)
        conn.commit()

    return db


def test_ws_tap_processing(db):
    process_tap(db, "tests/logs_ingestion/data/taps/http/ws.json")

    assert_table(db, "http_request", expect=[{"is_websocket": 1}])
    assert_table(db, "websocket_connection", expect=[{"http_request_id": 1}])
    assert_table(
        db,
        "websocket_frame",
        expect=[
            {"is_client": 1, "payload_text": "Hello WebSocket!"},
            {"is_client": 1, "payload_text": '{"type": "echo", "message": "Hello from JSON"}'},
            {"is_client": 1, "payload_text": '{"type": "ping", "timestamp": 1761121825}'},
            {"is_client": 1, "payload_text": '{"type": "unknown", "data": "test"}'},
            {"is_client": 1, "payload_text": "\x03"},
            {"is_client": 0, "payload_text": "Echo: Hello WebSocket!"},
            {"is_client": 0, "payload_text": '{"type": "echo", "message": "Hello from JSON"}'},
            {"is_client": 0, "payload_text": '{"type": "pong", "timestamp": 1761121825}'},
            {
                "is_client": 0,
                "payload_text": '{"type": "error", "message": "Unknown type: unknown"}',
            },
            {"is_client": 0, "payload_text": "\x03"},
        ],
    )
