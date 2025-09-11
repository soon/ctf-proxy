import tempfile
import time
from pathlib import Path

import yaml

from ctf_proxy.config.config import Config


def test_config_file_watching():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        initial_config = {"services": [{"name": "web", "port": 8080, "type": "http"}]}
        yaml.dump(initial_config, f)
        f.flush()

        config_path = Path(f.name)

    try:
        config = Config(config_path)
        assert len(config.services) == 1
        assert config.services[0].name == "web"

        config.start_watching()
        assert config.is_watching()

        time.sleep(0.5)

        updated_config = {
            "services": [
                {"name": "web", "port": 8080, "type": "http"},
                {"name": "api", "port": 3000, "type": "http"},
            ]
        }

        with open(config_path, "w") as f:
            yaml.dump(updated_config, f)

        time.sleep(2.0)

        assert len(config.services) == 2
        assert config.get_service_by_name("api") is not None
        assert config.get_service_by_name("api").port == 3000

        config.stop_watching()
        assert not config.is_watching()

    finally:
        config_path.unlink(missing_ok=True)


def test_config_context_manager():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        config_data = {"services": [{"name": "test", "port": 9000, "type": "tcp"}]}
        yaml.dump(config_data, f)
        f.flush()

        config_path = Path(f.name)

    try:
        with Config(config_path) as config:
            config.start_watching()
            assert config.is_watching()

        assert not config.is_watching()

    finally:
        config_path.unlink(missing_ok=True)


def test_config_reload_with_invalid_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        initial_config = {"services": [{"name": "web", "port": 8080, "type": "http"}]}
        yaml.dump(initial_config, f)
        f.flush()

        config_path = Path(f.name)

    try:
        config = Config(config_path)
        original_services = config.services.copy()

        config.start_watching()

        time.sleep(0.1)

        with open(config_path, "w") as f:
            f.write("invalid: yaml: content: [")

        time.sleep(1.0)

        assert config.services == original_services

        config.stop_watching()

    finally:
        config_path.unlink(missing_ok=True)
