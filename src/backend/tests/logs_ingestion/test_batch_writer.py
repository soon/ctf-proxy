from types import SimpleNamespace

import psycopg
import pytest

from ctf_proxy.db.models import (
    FlagRow,
    HttpRequestRow,
    HttpResponseRow,
    SessionLinkRow,
)
from ctf_proxy.logs_ingestion.batch_writer import (
    Batch,
    flush_with_isolation_fallback,
    insert_rows,
    is_bad_row_error,
)
from tests.utils import assert_table


def request_insert(port=80, **overrides):
    params = {
        "port": port,
        "start_time": 1000,
        "path": "/",
        "method": "GET",
        "is_blocked": 0,
    }
    params.update(overrides)
    return HttpRequestRow.Insert(**params)


def flush(db, batch):
    with db.connect() as conn:
        tx = conn.cursor()
        flush_with_isolation_fallback(
            tx, lambda isolate: batch.flush(tx, isolate=isolate), batch.reset
        )
        conn.commit()


def test_ref_chain_links_request_response_flag(db):
    batch = Batch()
    req = batch.insert(request_insert(path="/a"))
    resp = batch.insert(HttpResponseRow.Insert(request_id=req, status=200))
    batch.insert_many(
        [
            FlagRow.Insert(value="flag_in", http_request_id=req, location="body"),
            FlagRow.Insert(value="flag_out", http_response_id=resp, location="body"),
        ]
    )
    flush(db, batch)

    assert req.resolved and resp.resolved
    assert_table(db, "http_request", expect=[{"id": req.value, "path": "/a"}])
    assert_table(db, "http_response", expect=[{"request_id": req.value, "status": 200}])
    assert_table(
        db,
        "flag",
        expect=[
            {"value": "flag_in", "http_request_id": req.value, "http_response_id": None},
            {"value": "flag_out", "http_request_id": None, "http_response_id": resp.value},
        ],
    )


def test_bad_row_isolated_others_survive(db):
    batch = Batch()
    batch.insert(request_insert(path="/ok1"))
    batch.insert(request_insert(path="/bad", port=None))
    batch.insert(request_insert(path="/ok2"))
    flush(db, batch)

    assert_table(db, "http_request", expect=[{"path": "/ok1"}, {"path": "/ok2"}])


def test_bad_parent_cascades_to_dependent(db):
    batch = Batch()
    bad_req = batch.insert(request_insert(port=None))
    batch.insert(HttpResponseRow.Insert(request_id=bad_req, status=200))
    flush(db, batch)

    assert not bad_req.resolved
    assert_table(db, "http_request", expect=[])
    assert_table(db, "http_response", expect=[])


def test_is_bad_row_error_classification():
    assert is_bad_row_error(SimpleNamespace(sqlstate="23502")) is True  # not-null violation
    assert is_bad_row_error(SimpleNamespace(sqlstate="22021")) is True  # invalid byte seq
    assert is_bad_row_error(SimpleNamespace(sqlstate="54000")) is True  # index row too big
    assert is_bad_row_error(SimpleNamespace(sqlstate="42P01")) is False  # undefined table (code bug)
    assert is_bad_row_error(SimpleNamespace(sqlstate="57P01")) is False  # admin shutdown
    assert is_bad_row_error(SimpleNamespace(sqlstate=None)) is False  # connection lost


def test_transient_error_propagates_not_dropped(db):
    # a non-data error (undefined table, 42P01) must propagate, never be swallowed as a
    # dropped row — this is what stops connection loss / shutdown from silently dropping data.
    with db.connect() as conn:
        tx = conn.cursor()
        with pytest.raises(psycopg.Error):
            insert_rows(tx, "no_such_table", ["a"], [[1]], isolate=True)


def test_session_dedup_counts_occurrences(db):
    batch = Batch()
    req1 = batch.insert(request_insert(path="/1"))
    req2 = batch.insert(request_insert(path="/2"))
    s1 = batch.session(80, "sess-a")
    s2 = batch.session(80, "sess-a")
    batch.insert(SessionLinkRow.Insert(session_id=s1, http_request_id=req1))
    batch.insert(SessionLinkRow.Insert(session_id=s2, http_request_id=req2))
    flush(db, batch)

    assert s1 is s2 and s1.resolved
    assert_table(db, "session", expect=[{"key": "sess-a", "count": 2}])
    assert_table(db, "session_link", expect=[{"session_id": s1.value}, {"session_id": s1.value}])
