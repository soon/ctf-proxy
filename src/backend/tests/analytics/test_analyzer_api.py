import textwrap

import pytest
from fastapi.testclient import TestClient

from ctf_proxy.analytics import api
from ctf_proxy.db.models import make_db
from ctf_proxy.db.utils import now_timestamp

ADMIN_RULE = textwrap.dedent(
    """
    from ctf_proxy.analytics.rule import Match, PatternRule

    class AdminRule(PatternRule):
        name = "admin_probe"

        def match(self, ctx):
            if ctx.path.lower().startswith("/admin"):
                yield Match(tag="admin_probe", meta=ctx.path)
    """
)

PORT_RULE = textwrap.dedent(
    """
    from ctf_proxy.analytics.rule import Match, PatternRule

    class PortRule(PatternRule):
        name = "port_rule"
        port = 8081

        def match(self, ctx):
            yield Match(tag="any", meta=ctx.path)
    """
)

ENABLED_RULE = textwrap.dedent(
    """
    from ctf_proxy.analytics.rule import Match, PatternRule

    class EnabledRule(PatternRule):
        name = "enabled_one"

        def match(self, ctx):
            yield Match(tag="enabled", meta=ctx.path)
    """
)


def seed_source_db() -> dict[str, int]:
    db = make_db()
    with db.connect() as conn:
        tx = conn.cursor()
        admin_id = db.http_requests.insert(
            tx, port=8080, start_time=now_timestamp(), path="/admin/users", method="GET"
        )
        home_id = db.http_requests.insert(
            tx, port=8081, start_time=now_timestamp(), path="/home", method="GET"
        )
        conn.commit()
    return {"admin_id": admin_id, "home_id": home_id}


@pytest.fixture
def client():
    ids = seed_source_db()
    api.init_app()
    with api.analysis_db.connect() as conn:
        tx = conn.cursor()
        api.analysis_db.rules_source.upsert(tx, "enabled_one", "enabled", ENABLED_RULE, 1)
        conn.commit()
    test_client = TestClient(api.app)
    test_client.ids = ids
    return test_client


def test_tag_stats_empty_initially(client):
    resp = client.get("/api/tag-stats", params={"port": 8080})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"port": 8080, "window_minutes": 60, "tags": []}


def test_backfill_create_and_get(client):
    resp = client.post("/api/backfill", json={"ports": [8080]})
    assert resp.status_code == 200
    job = resp.json()
    assert job["status"] == "pending"
    assert job["ports"] == [8080]
    assert job["target_id"] >= 1

    resp = client.get("/api/backfill")
    assert resp.status_code == 200
    assert resp.json()["id"] == job["id"]


def test_backfill_for_port(client):
    resp = client.post("/api/backfill", json={"ports": [8080]})
    assert resp.status_code == 200
    job = resp.json()
    assert job["ports"] == [8080]
    assert job["status"] == "pending"


def test_backfill_ignores_rule_name(client):
    resp = client.post("/api/backfill", json={"rule_name": "enabled_one"})
    assert resp.status_code == 200
    assert "rule_name" not in resp.json()


def test_backfill_returns_the_job_it_created(client):
    first = client.post("/api/backfill", json={"ports": [8080]}).json()
    second = client.post("/api/backfill", json={"ports": [8081]}).json()
    assert second["id"] != first["id"]
    assert second["ports"] == [8081]


def test_tags_for_refs_filters_by_rule(client):
    resp = client.post(
        "/api/tags/for-refs",
        json={"source_type": "http", "ids": [1, 2], "rules": ["nope"]},
    )
    assert resp.status_code == 200
    assert resp.json() == {"tags": {}}


def test_list_rules_includes_enabled(client):
    resp = client.get("/api/analyzer_health_check")  # sanity: wrong path 404
    assert resp.status_code == 404

    resp = client.get("/api/rules")
    assert resp.status_code == 200
    rules = resp.json()["rules"]
    assert {"name": "enabled_one", "status": "enabled", "port": None, "error": None} in rules


def test_save_get_and_list_draft(client):
    resp = client.put("/api/rules/admin_probe", json={"source": ADMIN_RULE})
    assert resp.status_code == 200

    resp = client.get("/api/rules/admin_probe", params={"status": "draft"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "admin_probe"
    assert body["status"] == "draft"
    assert "class AdminRule" in body["source"]

    names = {(r["name"], r["status"]) for r in client.get("/api/rules").json()["rules"]}
    assert ("admin_probe", "draft") in names
    assert ("enabled_one", "enabled") in names


def test_preview_matches_selected_ids(client):
    resp = client.post(
        "/api/preview",
        json={
            "source": ADMIN_RULE,
            "source_type": "http",
            "ids": [client.ids["admin_id"], client.ids["home_id"]],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scanned"] == 2
    assert body["count"] == 1
    assert body["matches"][0]["ref_id"] == client.ids["admin_id"]
    assert body["matches"][0]["tag"] == "admin_probe"


def test_preview_respects_rule_port(client):
    resp = client.post(
        "/api/preview",
        json={
            "source": PORT_RULE,
            "source_type": "http",
            "ids": [client.ids["admin_id"], client.ids["home_id"]],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["matches"][0]["port"] == 8081
    assert body["matches"][0]["ref_id"] == client.ids["home_id"]


def test_promote_moves_draft_to_enabled(client):
    client.put("/api/rules/admin_probe", json={"source": ADMIN_RULE})

    resp = client.post("/api/rules/admin_probe/promote")
    assert resp.status_code == 200

    rules = {(r["name"], r["status"]) for r in client.get("/api/rules").json()["rules"]}
    assert ("admin_probe", "enabled") in rules
    assert ("admin_probe", "draft") not in rules

    assert client.get("/api/rules/admin_probe", params={"status": "enabled"}).status_code == 200


def test_delete_rule(client):
    client.put("/api/rules/admin_probe", json={"source": ADMIN_RULE})
    assert client.delete("/api/rules/admin_probe", params={"status": "draft"}).status_code == 200
    assert client.get("/api/rules/admin_probe", params={"status": "draft"}).status_code == 404


def test_invalid_name_rejected(client):
    resp = client.put("/api/rules/bad name!", json={"source": ADMIN_RULE})
    assert resp.status_code == 400


def test_missing_rule_returns_404(client):
    resp = client.get("/api/rules/nope", params={"status": "draft"})
    assert resp.status_code == 404


def test_broken_source_rejected_on_save(client):
    resp = client.put("/api/rules/broken", json={"source": "def not valid python !!!"})
    assert resp.status_code == 400


def test_source_without_rule_rejected(client):
    resp = client.put("/api/rules/norule", json={"source": "x = 1\n"})
    assert resp.status_code == 400


def test_preview_broken_source_returns_400(client):
    resp = client.post(
        "/api/preview",
        json={"source": "def not valid !!!", "source_type": "http", "ids": [1]},
    )
    assert resp.status_code == 400
