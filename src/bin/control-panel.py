#!/usr/bin/env python3
"""Control panel for CTF Proxy management."""

import argparse
import shutil
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


def read_config(config_path: Path) -> dict[str, Any]:
    """Read configuration from YAML file."""
    yaml = YAML()
    with open(config_path) as f:
        return yaml.load(f)


def ensure_docker_compose(template_path: Path, compose_path: Path) -> None:
    """Ensure docker-compose.yml exists, copying from template if needed."""
    if not compose_path.exists():
        shutil.copy2(template_path, compose_path)
        print("Copied docker-compose.yml from template")


def update_docker_compose_with_mounts(compose_path: Path, config: dict[str, Any]) -> None:
    """Update docker-compose.yml to include mounts from config."""
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    with open(compose_path) as f:
        compose_data = yaml.load(f)

    # Get mount folders from services in config
    mount_folders = set()
    if "services" in config:
        for service in config["services"]:
            if "mount_folder" in service:
                mount_folders.add(service["mount_folder"])

    # Add mounts to envoy service volumes
    if "services" in compose_data and "envoy" in compose_data["services"]:
        envoy = compose_data["services"]["envoy"]
        if "volumes" not in envoy:
            envoy["volumes"] = []

        # Add mount folders as volumes
        for mount_folder in sorted(mount_folders):
            volume_entry = f"{mount_folder}:{mount_folder}:ro"
            if volume_entry not in envoy["volumes"]:
                envoy["volumes"].append(volume_entry)

    # Write back the updated compose file
    with open(compose_path, "w") as f:
        yaml.dump(compose_data, f)

    print(f"Updated docker-compose.yml with {len(mount_folders)} mount(s)")


def start_command() -> None:
    """Execute the start command."""
    # Define paths
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / "src" / "data" / "config.yml"
    template_path = project_root / "src" / "docker-compose.template.yml"
    compose_path = project_root / "src" / "docker-compose.yml"

    # Read config
    if not config_path.exists():
        print(f"Error: Config file not found at {config_path}")
        return

    config = read_config(config_path)
    print(f"Read config from {config_path}")

    # Ensure docker-compose.yml exists
    ensure_docker_compose(template_path, compose_path)

    # Update docker-compose with mounts
    update_docker_compose_with_mounts(compose_path, config)

    print("Start command completed successfully")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="CTF Proxy Control Panel")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Start command
    subparsers.add_parser("start", help="Start the CTF proxy services")

    args = parser.parse_args()

    if args.command == "start":
        start_command()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
