from ctf_proxy.logs_ingestion.batch_stats import BatchStats
from tests.utils import assert_table


def flush(db, batch: BatchStats):
    with db.connect() as conn:
        tx = conn.cursor()
        batch.flush(tx)
        conn.commit()


def test_header_time_stats_aggregate_same_key(db):
    batch = BatchStats()
    batch.add_header_time(port=80, name="host", value="a", time=60, count=1)
    batch.add_header_time(port=80, name="host", value="a", time=60, count=1)
    batch.add_header_time(port=80, name="host", value="b", time=60, count=1)
    flush(db, batch)

    assert_table(
        db,
        "http_header_time_stats",
        expect=[{"value": "a", "count": 2}, {"value": "b", "count": 1}],
    )


def test_flush_upserts_across_batches(db):
    first = BatchStats()
    first.add_request_time(port=80, time=60, count=3, blocked_count=1)
    flush(db, first)

    second = BatchStats()
    second.add_request_time(port=80, time=60, count=2, blocked_count=2)
    flush(db, second)

    assert_table(
        db,
        "http_request_time_stats",
        expect=[{"port": 80, "count": 5, "blocked_count": 3}],
    )


def test_service_stats_sum(db):
    batch = BatchStats()
    batch.add_service(port=80, total_requests=1, total_responses=1)
    batch.add_service(port=80, total_requests=1, total_blocked_requests=1)
    flush(db, batch)

    assert_table(
        db,
        "service_stats",
        expect=[{"total_requests": 2, "total_responses": 1, "total_blocked_requests": 1}],
    )


def test_empty_flush_is_noop(db):
    flush(db, BatchStats())
    assert_table(db, "http_header_time_stats", expect=[])
