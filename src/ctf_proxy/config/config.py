import logging
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from ctf_proxy.utils.watcher import Watcher

logger = logging.getLogger(__name__)


class ServiceType(Enum):
    HTTP = "http"
    TCP = "tcp"
    UDP = "udp"
    WS = "ws"


class IgnoredPathStat(BaseModel):
    method: str = Field(..., min_length=1, description="HTTP method to ignore (e.g., GET, POST)")
    path: str = Field(
        ..., min_length=1, description="Path to ignore (e.g., /api/v1/resource, can be regex)"
    )


class Service(BaseModel):
    name: str = Field(..., min_length=1, description="Service name")
    port: int = Field(..., ge=1, le=65535, description="Service port number")
    type: ServiceType = Field(..., description="Service type")
    ignore_path_stats: list[IgnoredPathStat] = Field(
        default_factory=list,
        description="List of ignored path stats",
    )
    ignore_query_param_stats: dict[str, str] = Field(
        default_factory=dict,
        description="Query parameters to ignore in stats (key-value pairs)",
    )
    ignore_header_stats: dict[str, str] = Field(
        default_factory=dict,
        description="Headers to ignore in stats (key-value pairs)",
    )
    session_cookie_names: list[str] = Field(
        default_factory=lambda: [
            "session",
            "sessid",
            "sid",
            "token",
            "auth",
            "sessionid",
            ".AspNetCore.Identity.Application",
        ],
        description="Cookie names to track for session management",
    )


class ConfigError(Exception):
    pass


class ConfigModel(BaseModel):
    flag_format: str = Field(default="ctf{}", description="Flag format string")
    services: list[Service] = Field(default_factory=list, description="List of services")

    @field_validator("services")
    @classmethod
    def validate_unique_ports(cls, v: list[Service]) -> list[Service]:
        used_ports = set()
        for service in v:
            if service.port in used_ports:
                raise ValueError(f"Port {service.port} is already used by another service")
            used_ports.add(service.port)
        return v


class Config:
    flag_format: str
    services: list[Service]

    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self._watcher: Watcher | None = None
        self._config = None
        self.load_config()

    def __getattr__(self, name):
        if self._config is not None:
            return getattr(self._config, name)
        raise AttributeError("Config not loaded")

    def load_config(self) -> None:
        if not self.config_path.exists():
            raise ConfigError(f"Configuration file not found: {self.config_path}")

        try:
            with open(self.config_path) as f:
                config_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in configuration file: {e}") from e
        except Exception as e:
            raise ConfigError(f"Failed to read configuration file: {e}") from e

        if config_data is None:
            config_data = {}

        if not isinstance(config_data, dict):
            raise ConfigError("Configuration must be a YAML object")

        try:
            self._config = ConfigModel(**config_data)
        except ValidationError as e:
            raise ConfigError("Configuration validation error") from e

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

    def start_watching(self) -> None:
        if self._watcher is not None:
            return

        def on_config_change():
            try:
                self.load_config()
                logger.info("Config reloaded due to file change")
            except ConfigError:
                logger.error("Failed to reload config after file change")
                pass

        self._watcher = Watcher(self.config_path, on_config_change)
        self._watcher.start_watching()

    def stop_watching(self) -> None:
        if self._watcher is not None:
            self._watcher.stop_watching()
            self._watcher = None

    def is_watching(self) -> bool:
        return self._watcher is not None and self._watcher.is_watching()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_watching()

    def __repr__(self) -> str:
        return f"Config(services={len(self.services)})"
