import base64

from ctf_proxy.common.config import Config
from ctf_proxy.logs_ingestion.tcp import TcpTapProcessor
from tests.utils import assert_table

TS = "2024-01-01T00:00:00Z"


def data_event(kind: str, payload: bytes) -> dict:
    return {
        kind: {"data": {"as_bytes": base64.b64encode(payload).decode()}},
        "timestamp": TS,
    }


def test_tcp_events_batch_insert(db):
    config = Config("tests/logs_ingestion/data/test-config.yaml")
    processor = TcpTapProcessor(db=db, config=config)

    data = {
        "socket_buffered_trace": {
            "events": [
                data_event("read", b"hello"),
                data_event("write", b"world"),
                {"closed": {}, "timestamp": TS},
            ]
        }
    }
    log_entry = {
        "upstream_host": "127.0.0.1:1234",
        "start_time": TS,
        "connection_id": 7,
        "bytes_in": 5,
        "bytes_out": 5,
        "duration_ms": 1,
    }

    with db.connect() as conn:
        tx = conn.cursor()
        processor.process_tap(tx, data, tap_id="t", batch_id="b", log_entry=log_entry)
        conn.commit()

    assert_table(
        db,
        "tcp_event",
        expect=[
            {"event_type": "read", "data_text": "hello", "data_size": 5},
            {"event_type": "write", "data_text": "world", "data_size": 5},
            {"event_type": "closed", "data_size": 0},
        ],
    )
