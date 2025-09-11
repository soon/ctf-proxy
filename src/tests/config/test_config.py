import tempfile
from pathlib import Path

import pytest

from ctf_proxy.config import Config, ConfigError, Service, ServiceType


class TestService:
    def test_create_service(self):
        service = Service("web", 8080, "http")
        assert service.name == "web"
        assert service.port == 8080
        assert service.type == ServiceType.HTTP

    def test_service_equality(self):
        service1 = Service("web", 8080, "http")
        service2 = Service("web", 8080, "http")
        service3 = Service("api", 8080, "http")

        assert service1 == service2
        assert service1 != service3

    def test_service_repr(self):
        service = Service("web", 8080, "http")
        assert repr(service) == "Service(name='web', port=8080, type=http)"

    def test_invalid_service_type(self):
        with pytest.raises(ValueError):
            Service("web", 8080, "invalid")


class TestConfig:
    def test_load_valid_config(self):
        config_content = """
services:
  - name: web
    port: 8080
    type: http
  - name: database
    port: 5432
    type: tcp
  - name: websocket
    port: 3000
    type: ws
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            config = Config(temp_path)
            assert len(config.services) == 3

            web_service = config.get_service_by_name("web")
            assert web_service is not None
            assert web_service.port == 8080
            assert web_service.type == ServiceType.HTTP

            db_service = config.get_service_by_port(5432)
            assert db_service is not None
            assert db_service.name == "database"
            assert db_service.type == ServiceType.TCP
        finally:
            Path(temp_path).unlink()

    def test_config_file_not_found(self):
        with pytest.raises(ConfigError, match="Configuration file not found"):
            Config("/nonexistent/file.yml")

    def test_invalid_yaml(self):
        config_content = """
services:
  - name: web
    port: 8080
    type: http
  - invalid: [yaml content
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            with pytest.raises(ConfigError, match="Invalid YAML"):
                Config(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_missing_services_field(self):
        config_content = """
not_services:
  - name: web
    port: 8080
    type: http
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            config = Config(temp_path)
            assert len(config.services) == 0
        finally:
            Path(temp_path).unlink()

    def test_services_not_list(self):
        config_content = """
services: not_a_list
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            with pytest.raises(ConfigError, match="'services' must be a list"):
                Config(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_duplicate_ports(self):
        config_content = """
services:
  - name: web1
    port: 8080
    type: http
  - name: web2
    port: 8080
    type: tcp
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            with pytest.raises(ConfigError, match="Port 8080 is already used"):
                Config(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_missing_required_fields(self):
        config_content = """
services:
  - name: web
    type: http
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            with pytest.raises(ConfigError, match="Service 'port' is required"):
                Config(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_invalid_port_values(self):
        test_cases = [
            (-1, "Service port must be between 1 and 65535"),
            (0, "Service port must be between 1 and 65535"),
            (65536, "Service port must be between 1 and 65535"),
        ]

        for port, expected_error in test_cases:
            config_content = f"""
services:
  - name: web
    port: {port}
    type: http
"""
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
                f.write(config_content)
                temp_path = f.name

            try:
                with pytest.raises(ConfigError, match=expected_error):
                    Config(temp_path)
            finally:
                Path(temp_path).unlink()

    def test_invalid_service_type(self):
        config_content = """
services:
  - name: web
    port: 8080
    type: invalid_type
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            with pytest.raises(ConfigError, match="Invalid service type 'invalid_type'"):
                Config(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_get_services_by_type(self):
        config_content = """
services:
  - name: web1
    port: 8080
    type: http
  - name: web2
    port: 8081
    type: http
  - name: database
    port: 5432
    type: tcp
  - name: websocket
    port: 3000
    type: ws
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            config = Config(temp_path)

            http_services = config.get_services_by_type(ServiceType.HTTP)
            assert len(http_services) == 2
            assert all(s.type == ServiceType.HTTP for s in http_services)

            tcp_services = config.get_services_by_type(ServiceType.TCP)
            assert len(tcp_services) == 1
            assert tcp_services[0].name == "database"

            udp_services = config.get_services_by_type(ServiceType.UDP)
            assert len(udp_services) == 0
        finally:
            Path(temp_path).unlink()

    def test_config_repr(self):
        config_content = """
services:
  - name: web
    port: 8080
    type: http
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            config = Config(temp_path)
            assert repr(config) == "Config(services=1)"
        finally:
            Path(temp_path).unlink()


class TestServiceType:
    def test_service_type_values(self):
        assert ServiceType.HTTP.value == "http"
        assert ServiceType.TCP.value == "tcp"
        assert ServiceType.UDP.value == "udp"
        assert ServiceType.WS.value == "ws"
