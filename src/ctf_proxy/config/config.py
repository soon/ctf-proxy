from enum import Enum
from pathlib import Path

import yaml


class ServiceType(Enum):
    HTTP = "http"
    TCP = "tcp"
    UDP = "udp"
    WS = "ws"


class Service:
    def __init__(self, name: str, port: int, service_type: str):
        self.name = name
        self.port = port
        self.type = ServiceType(service_type)

    def __repr__(self) -> str:
        return f"Service(name='{self.name}', port={self.port}, type={self.type.value})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Service):
            return False
        return self.name == other.name and self.port == other.port and self.type == other.type


class ConfigError(Exception):
    pass


class Config:
    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self.services: list[Service] = []
        self._load_config()

    def _load_config(self) -> None:
        if not self.config_path.exists():
            raise ConfigError(f"Configuration file not found: {self.config_path}")

        try:
            with open(self.config_path) as f:
                config_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in configuration file: {e}") from e
        except Exception as e:
            raise ConfigError(f"Failed to read configuration file: {e}") from e

        if not isinstance(config_data, dict):
            raise ConfigError("Configuration must be a YAML object")

        services_data = config_data.get("services", [])
        if not isinstance(services_data, list):
            raise ConfigError("'services' must be a list")

        self.services = []
        used_ports = set()

        for service_data in services_data:
            if not isinstance(service_data, dict):
                raise ConfigError("Each service must be an object")

            name = service_data.get("name")
            port = service_data.get("port")
            service_type = service_data.get("type")

            if not name:
                raise ConfigError("Service 'name' is required")
            if not isinstance(name, str):
                raise ConfigError("Service 'name' must be a string")

            if port is None:
                raise ConfigError("Service 'port' is required")
            if not isinstance(port, int):
                raise ConfigError("Service 'port' must be an integer")
            if port <= 0 or port > 65535:
                raise ConfigError(f"Service port must be between 1 and 65535, got: {port}")

            if port in used_ports:
                raise ConfigError(f"Port {port} is already used by another service")
            used_ports.add(port)

            if not service_type:
                raise ConfigError("Service 'type' is required")
            if not isinstance(service_type, str):
                raise ConfigError("Service 'type' must be a string")

            try:
                ServiceType(service_type)
            except ValueError as e:
                valid_types = [t.value for t in ServiceType]
                raise ConfigError(f"Invalid service type '{service_type}'. Valid types: {valid_types}") from e

            service = Service(name, port, service_type)
            self.services.append(service)

    def get_service_by_name(self, name: str) -> Service | None:
        for service in self.services:
            if service.name == name:
                return service
        return None

    def get_service_by_port(self, port: int) -> Service | None:
        for service in self.services:
            if service.port == port:
                return service
        return None

    def get_services_by_type(self, service_type: ServiceType) -> list[Service]:
        return [service for service in self.services if service.type == service_type]

    def __repr__(self) -> str:
        return f"Config(services={len(self.services)})"
