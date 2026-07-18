import textwrap

from ctf_proxy.analytics.db import make_analysis_db
from ctf_proxy.analytics.registry import RuleRegistry
from ctf_proxy.analytics.runner import HTTP_SOURCE, TCP_SOURCE, AnalyzerRunner
from ctf_proxy.db.analysis import AnalysisDB
from ctf_proxy.db.models import make_db
from ctf_proxy.db.utils import now_timestamp

SQLI_RULE = textwrap.dedent(
    """
    from ctf_proxy.analytics.rule import Match, PatternRule

    class SqliRule(PatternRule):
        name = "sqli"

        def match(self, ctx):
            if "or '1'='1" in ctx.path.lower():
                yield Match(tag="sqli", meta=ctx.path)
    """
)

PATH_RULE = textwrap.dedent(
    """
    from ctf_proxy.analytics.rule import Match, PatternRule

    class PathRule(PatternRule):
        name = "path"

        def match(self, ctx):
            if "or '1'='1" in ctx.path.lower():
                yield Match(tag="path", meta=ctx.path)
    """
)

TCP_RULE = textwrap.dedent(
    """
    from ctf_proxy.analytics.rule import Match, PatternRule

    class TcpShellRule(PatternRule):
        name = "tcp_shell"

        def match_tcp(self, ctx):
            if "cat flag" in ctx.text.lower():
                yield Match(tag="tcp_shell", meta=str(ctx.connection_id))
    """
)

CRASHING_RULE = textwrap.dedent(
    """
    from ctf_proxy.analytics.rule import PatternRule

    class BoomRule(PatternRule):
        name = "boom"

        def match(self, ctx):
            raise RuntimeError("boom")
    """
)


def seed_source_db() -> dict[str, int]:
    source = make_db()
    with source.connect() as conn:
        tx = conn.cursor()
        attack_id = source.http_requests.insert(
            tx,
            port=8080,
            start_time=now_timestamp(),
            path="/login?q=' OR '1'='1",
            method="GET",
        )
        source.http_responses.insert(tx, request_id=attack_id, status=200, body="ok")
        benign_id = source.http_requests.insert(
            tx,
            port=8080,
            start_time=now_timestamp(),
            path="/home",
            method="GET",
        )
        source.http_responses.insert(tx, request_id=benign_id, status=200, body="hi")

        shell_conn_id = source.tcp_connections.insert(
            tx,
            port=9000,
            connection_id=42,
            start_time=now_timestamp(),
            duration_ms=10,
            bytes_in=5,
            bytes_out=5,
        )
        source.tcp_events.insert(
            tx,
            connection_id=shell_conn_id,
            timestamp=now_timestamp(),
            event_type="read",
            data_text="cat flag.txt",
            data_size=12,
        )
        conn.commit()
    return {"attack_id": attack_id, "benign_id": benign_id, "shell_conn_id": shell_conn_id}


def read_results(runner: AnalyzerRunner) -> list[tuple]:
    with runner.db.connect() as conn:
        return conn.execute(
            "SELECT r.name, h.tag, h.meta, h.port, h.http_request_id "
            "FROM http_analysis_result h JOIN rule r ON r.id = h.rule_id ORDER BY h.id"
        ).fetchall()


def cursor_for(runner: AnalyzerRunner, rule_name: str, source: str) -> int:
    with runner.db.connect() as conn:
        row = conn.execute(
            "SELECT c.last_id FROM analysis_cursor c JOIN rule r ON r.id = c.rule_id "
            "WHERE r.name = %s AND c.source = %s",
            (rule_name, source),
        ).fetchone()
    return row[0] if row else 0


def seed_rule(db: AnalysisDB, name: str, source: str, status: str = "enabled") -> None:
    with db.connect() as conn:
        tx = conn.cursor()
        db.rules_source.upsert(tx, name, status, source, db.rules_source.max_updated(tx) + 1)
        conn.commit()


def make_runner(rule_source: str) -> tuple[AnalyzerRunner, dict[str, int]]:
    ids = seed_source_db()
    runner = AnalyzerRunner(batch_size=500)
    seed_rule(runner.db, "rule", rule_source)
    runner.registry.maybe_reload()
    return runner, ids


def test_process_batch_writes_matches_and_advances_cursor():
    runner, ids = make_runner(SQLI_RULE)

    processed = runner.process_batch()
    assert processed == 3

    results = read_results(runner)
    assert results == [("sqli", "sqli", "/login?q=' OR '1'='1", 8080, ids["attack_id"])]

    assert cursor_for(runner, "sqli", HTTP_SOURCE) == ids["benign_id"]

    assert runner.process_batch() == 0
    assert len(read_results(runner)) == 1


def test_tcp_rule_writes_connection_match():
    runner, ids = make_runner(TCP_RULE)

    assert runner.process_batch() == 3

    with runner.db.connect() as conn:
        rows = conn.execute(
            "SELECT r.name, t.tag, t.port, t.tcp_connection_id "
            "FROM tcp_analysis_result t JOIN rule r ON r.id = t.rule_id ORDER BY t.id"
        ).fetchall()
    assert rows == [("tcp_shell", "tcp_shell", 9000, ids["shell_conn_id"])]

    assert cursor_for(runner, "tcp_shell", TCP_SOURCE) == ids["shell_conn_id"]

    assert runner.process_batch() == 0


def test_crashing_rule_is_isolated():
    runner, _ = make_runner(CRASHING_RULE)

    assert runner.process_batch() == 3
    assert read_results(runner) == []
    assert cursor_for(runner, "boom", HTTP_SOURCE) > 0
    assert cursor_for(runner, "boom", TCP_SOURCE) > 0


def test_empty_source_db_does_not_crash():
    make_db()  # schema only, no rows

    runner = AnalyzerRunner()
    seed_rule(runner.db, "rule", SQLI_RULE)
    runner.registry.maybe_reload()
    assert runner.process_batch() == 0
    assert runner.source.max_source_id() == 0


def test_source_without_tables_returns_empty():
    runner = AnalyzerRunner()
    seed_rule(runner.db, "rule", SQLI_RULE)
    runner.registry.maybe_reload()
    assert runner.process_batch() == 0
    assert runner.source.max_source_id() == 0


def create_backfill(runner: AnalyzerRunner, target_id: int, ports=None) -> int:
    with runner.db.connect() as conn:
        tx = conn.cursor()
        job_id = runner.db.backfill.create(tx, target_id, ports, now_timestamp())
        conn.commit()
    return job_id


def drain_backfill(runner: AnalyzerRunner) -> None:
    for _ in range(10):
        if runner.process_backfill_batch() == 0:
            break


def test_backfill_reprocesses_range_after_rule_added():
    runner, ids = make_runner(SQLI_RULE)

    seed_rule(runner.db, "extra", PATH_RULE)
    runner.registry.maybe_reload()

    create_backfill(runner, target_id=ids["benign_id"], ports=[8080])

    processed = 0
    for _ in range(10):
        step = runner.process_backfill_batch()
        processed += step
        if step == 0:
            break

    results = read_results(runner)
    tags = {(name, ref) for name, _tag, _meta, _port, ref in results}
    assert ("sqli", ids["attack_id"]) in tags
    assert ("path", ids["attack_id"]) in tags

    with runner.db.connect() as conn:
        job = runner.db.backfill.active(conn.cursor())
    assert job is None


def tag_time_stats_sum(runner: AnalyzerRunner, port: int) -> int:
    with runner.db.connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(count), 0) FROM tag_time_stats WHERE port = %s", (port,)
        ).fetchone()
    return row[0]


def test_tag_time_stats_accumulate_and_stay_consistent():
    runner, ids = make_runner(SQLI_RULE)

    runner.process_batch()
    # one sqli match on the attack request (port 8080)
    assert tag_time_stats_sum(runner, 8080) == 1
    stats = runner.db.tag_stats(8080)
    assert stats and stats[0]["tag"] == "sqli" and stats[0]["total"] == 1
    series = runner.db.tag_time_series(8080, 0)
    assert series and series[0]["time_series"]

    # re-scan the same range via backfill must not double count
    create_backfill(runner, target_id=ids["benign_id"], ports=[8080])
    for _ in range(10):
        if runner.process_backfill_batch() == 0:
            break
    assert tag_time_stats_sum(runner, 8080) == 1


def test_backfill_is_idempotent():
    runner, ids = make_runner(SQLI_RULE)
    runner.process_batch()

    create_backfill(runner, target_id=ids["benign_id"], ports=[8080])
    for _ in range(10):
        if runner.process_backfill_batch() == 0:
            break

    results = read_results(runner)
    assert len(results) == 1
    assert results[0][:2] == ("sqli", "sqli")


def test_new_rule_backfills_independently():
    runner, ids = make_runner(SQLI_RULE)

    assert runner.process_batch() == 3
    assert runner.process_batch() == 0

    seed_rule(runner.db, "extra", PATH_RULE)
    assert runner.registry.maybe_reload() is True

    assert runner.process_batch() > 0

    results = read_results(runner)
    assert ("path", "path", "/login?q=' OR '1'='1", 8080, ids["attack_id"]) in results
    assert ("sqli", "sqli", "/login?q=' OR '1'='1", 8080, ids["attack_id"]) in results

    assert cursor_for(runner, "path", HTTP_SOURCE) == ids["benign_id"]
    assert cursor_for(runner, "sqli", HTTP_SOURCE) == ids["benign_id"]

    assert len([r for r in results if r[0] == "sqli"]) == 1


def test_registry_hot_reload_picks_up_new_rule():
    db = make_analysis_db()
    registry = RuleRegistry(db)

    assert registry.maybe_reload() is False
    assert registry.rules == []

    seed_rule(db, "rule", SQLI_RULE)
    assert registry.maybe_reload() is True
    assert [rule.rule_name() for rule in registry.rules] == ["sqli"]

    assert registry.maybe_reload() is False
