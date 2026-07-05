import importlib

import pytest
from fastapi.testclient import TestClient

dashboard_app = importlib.import_module("ctf_proxy.dashboard.app")


@pytest.fixture
def client(monkeypatch):
    calls = {}

    async def fake_request(method, path, *, params=None, json=None):
        calls["method"] = method
        calls["path"] = path
        calls["params"] = params
        calls["json"] = json
        if path == "/api/rules":
            return {"rules": [{"name": "r1", "status": "draft", "port": 8080, "error": None}]}
        if path.endswith("/promote"):
            return {"status": "promoted", "detail": "r1"}
        if path == "/api/preview":
            return {"matches": [], "count": 0, "scanned": 1}
        return {"status": "ok", "detail": None}

    monkeypatch.setattr(dashboard_app, "analyzer_request", fake_request)
    test_client = TestClient(dashboard_app.app)
    test_client.calls = calls
    return test_client


def test_proxy_list_rules(client):
    resp = client.get("/api/analyzer/rules", params={"port": 8080})
    assert resp.status_code == 200
    assert resp.json()["rules"][0]["name"] == "r1"
    assert client.calls["method"] == "GET"
    assert client.calls["path"] == "/api/rules"
    assert client.calls["params"] == {"port": 8080}


def test_proxy_save_rule(client):
    resp = client.put("/api/analyzer/rules/r1", json={"source": "code"})
    assert resp.status_code == 200
    assert client.calls["method"] == "PUT"
    assert client.calls["path"] == "/api/rules/r1"
    assert client.calls["json"] == {"source": "code"}


def test_proxy_promote(client):
    resp = client.post("/api/analyzer/rules/r1/promote")
    assert resp.status_code == 200
    assert resp.json()["status"] == "promoted"
    assert client.calls["path"] == "/api/rules/r1/promote"


def test_proxy_preview(client):
    resp = client.post(
        "/api/analyzer/preview",
        json={"source": "code", "source_type": "http", "ids": [1]},
    )
    assert resp.status_code == 200
    assert resp.json()["scanned"] == 1
    assert client.calls["path"] == "/api/preview"
