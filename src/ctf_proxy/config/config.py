import hashlib
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
    tcp_connection_stats_precision: int = Field(
        default=100, description="Precision for TCP connection stats buckets (bytes)"
    )


class ConfigError(Exception):
    pass


class ConfigModel(BaseModel):
    flag_format: str = Field(default="ctf{}", description="Flag format string")
    api_token_hash: str = Field(
        default="", description="SHA256 hash of API token for authentication"
    )
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


def hash_token(token: str) -> str:
    """Create SHA256 hash of token."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    """Verify token against stored hash."""
    return hash_token(token) == token_hash


class Config:
    flag_format: str
    tcp_connection_stats_precision: int
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

    @staticmethod
    def validate_content(content: str) -> tuple[bool, list[str]]:
        """Validate configuration content without loading it.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check YAML syntax
        try:
            config_data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            errors.append(f"Invalid YAML syntax: {str(e)}")
            return False, errors
        except Exception as e:
            errors.append(f"Failed to parse YAML: {str(e)}")
            return False, errors

        if config_data is None:
            config_data = {}

        if not isinstance(config_data, dict):
            errors.append("Configuration must be a YAML object")
            return False, errors

        # Validate with Pydantic model
        try:
            ConfigModel(**config_data)
        except ValidationError as e:
            for error in e.errors():
                field_path = " -> ".join(str(x) for x in error["loc"])
                errors.append(f"{field_path}: {error['msg']}")
            return False, errors
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
            return False, errors

        return True, []

    @classmethod
    def from_string(cls, content: str, config_path: str | Path) -> "Config":
        """Create Config instance from string content.

        Args:
            content: YAML configuration content
            config_path: Path where the config would be saved

        Returns:
            Config instance

        Raises:
            ConfigError: If content is invalid
        """
        # Validate content first
        valid, errors = cls.validate_content(content)
        if not valid:
            raise ConfigError(f"Invalid configuration: {'; '.join(errors)}")

        # Parse and create config
        config_data = yaml.safe_load(content)
        config_instance = cls.__new__(cls)
        config_instance.config_path = Path(config_path)
        config_instance._watcher = None
        config_instance._config = ConfigModel(**config_data)
        return config_instance

    @classmethod
    def from_file(cls, config_path: str | Path) -> "Config":
        """Create Config instance from file path.

        Args:
            config_path: Path to configuration file

        Returns:
            Config instance
        """
        return cls(config_path)

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

    def save(self, content: str, create_backup: bool = True) -> tuple[bool, str]:
        """Save configuration to file with optional backup.

        Args:
            content: YAML configuration content to save
            create_backup: Whether to create a backup of existing config

        Returns:
            Tuple of (success, message)
        """
        from datetime import datetime

        # Validate content first
        valid, errors = self.validate_content(content)
        if not valid:
            return False, f"Validation errors: {'; '.join(errors)}"

        try:
            # Create backup if requested and file exists
            if create_backup and self.config_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_dir = self.config_path.parent / "config_backups"
                backup_dir.mkdir(exist_ok=True)
                backup_path = backup_dir / f"config_{timestamp}.yml"

                with open(self.config_path) as f:
                    backup_content = f.read()
                with open(backup_path, "w") as f:
                    f.write(backup_content)

            # Save new config
            with open(self.config_path, "w") as f:
                f.write(content)

            # Reload config
            self.load_config()

            return True, "Configuration saved successfully"

        except Exception as e:
            return False, f"Failed to save configuration: {str(e)}"

    def get_revisions(self) -> list[dict]:
        """Get list of configuration backup revisions.

        Returns:
            List of revision dictionaries with filename, timestamp, and size
        """
        backup_dir = self.config_path.parent / "config_backups"
        if not backup_dir.exists():
            return []

        revisions = []
        for backup_file in sorted(backup_dir.glob("config_*.yml"), reverse=True):
            revisions.append(
                {
                    "filename": backup_file.name,
                    "timestamp": backup_file.stem.replace("config_", ""),
                    "size": backup_file.stat().st_size,
                }
            )
        return revisions

    def get_revision_content(self, filename: str) -> str | None:
        """Get content of a specific revision.

        Args:
            filename: Name of the revision file

        Returns:
            Content of the revision or None if not found
        """
        backup_dir = self.config_path.parent / "config_backups"
        revision_path = backup_dir / filename

        if not revision_path.exists():
            return None

        try:
            with open(revision_path) as f:
                return f.read()
        except Exception:
            return None

    def __repr__(self) -> str:
        return f"Config(services={len(self.services)})"
