import tempfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from ctf_proxy.dashboard.app import app, init_app
from ctf_proxy.db import ProxyStatsDB


@pytest.fixture
def temp_config():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        config_data = {
            "flag_format": "CTF{.*}",
            "services": [
                {"name": "web", "port": 8001, "type": "http"},
                {"name": "api", "port": 8002, "type": "http"},
                {"name": "tcp-service", "port": 9001, "type": "tcp"},
            ],
        }
        yaml.dump(config_data, f)
        config_path = f.name

    yield config_path

    Path(config_path).unlink(missing_ok=True)


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db = ProxyStatsDB(db_path)
    with db.connect() as conn:
        schema_path = Path(__file__).parent.parent.parent / "ctf_proxy" / "db" / "schema.sql"
        with open(schema_path) as schema_file:
            conn.executescript(schema_file.read())

        conn.execute(
            "INSERT INTO service_stats (port, total_requests, total_responses, total_blocked_requests, total_blocked_responses, total_flags_written, total_flags_retrieved, total_flags_blocked) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (8001, 100, 95, 5, 2, 10, 8, 1),
        )
        conn.execute(
            "INSERT INTO service_stats (port, total_requests, total_responses, total_blocked_requests, total_blocked_responses, total_flags_written, total_flags_retrieved, total_flags_blocked) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (8002, 50, 48, 2, 1, 5, 4, 0),
        )
        conn.execute(
            "INSERT INTO http_response_code_stats (port, status_code, count) VALUES (?, ?, ?)",
            (8001, 200, 80),
        )
        conn.execute(
            "INSERT INTO http_response_code_stats (port, status_code, count) VALUES (?, ?, ?)",
            (8001, 404, 10),
        )
        conn.execute(
            "INSERT INTO http_response_code_stats (port, status_code, count) VALUES (?, ?, ?)",
            (8001, 500, 5),
        )
        conn.commit()

    yield db_path

    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def client(temp_config, temp_db):
    init_app(temp_config, temp_db)
    return TestClient(app)


def test_get_services(client):
    response = client.get("/api/services")
    assert response.status_code == 200

    data = response.json()
    assert "services" in data
    assert "timestamp" in data
    assert len(data["services"]) == 3

    web_service = data["services"][0]
    assert web_service["name"] == "web"
    assert web_service["port"] == 8001
    assert web_service["type"] == "http"

    stats = web_service["stats"]
    assert stats["total_requests"] == 100
    assert stats["total_responses"] == 95
    assert stats["blocked_requests"] == 5
    assert stats["blocked_responses"] == 2
    assert stats["flags_written"] == 10
    assert stats["flags_retrieved"] == 8
    assert stats["flags_blocked"] == 1
    assert stats["status_counts"]["200"] == 80
    assert stats["status_counts"]["404"] == 10
    assert stats["status_counts"]["500"] == 5


def test_get_service_by_port(client):
    response = client.get("/api/services/8001")
    assert response.status_code == 200

    service_data = response.json()
    assert service_data["name"] == "web"
    assert service_data["port"] == 8001
    assert service_data["type"] == "http"

    stats = service_data["stats"]
    assert stats["total_requests"] == 100
    assert stats["total_responses"] == 95


def test_get_service_not_found(client):
    response = client.get("/api/services/9999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_multiple_service_types(client):
    response = client.get("/api/services")
    assert response.status_code == 200

    data = response.json()
    services = data["services"]

    service_types = [s["type"] for s in services]
    assert "http" in service_types
    assert "tcp" in service_types

    tcp_service = next(s for s in services if s["type"] == "tcp")
    assert tcp_service["name"] == "tcp-service"
    assert tcp_service["port"] == 9001
