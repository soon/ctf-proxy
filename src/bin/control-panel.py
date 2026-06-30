#!/usr/bin/env python3
"""Control panel for CTF Proxy management."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


def read_config(config_path: Path) -> dict[str, Any]:
    """Read configuration from YAML file."""
    yaml = YAML()
    with open(config_path) as f:
        return yaml.load(f)


def ensure_docker_compose(template_path: Path, compose_path: Path) -> None:
    """Regenerate docker-compose.yml from the template."""
    shutil.copy2(template_path, compose_path)
    print("Generated docker-compose.yml from template")


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


def generate_traefik_config(src_dir: Path, config_path: Path) -> None:
    """Generate the traefik dynamic configuration from config."""
    traefik_dir = src_dir / "traefik"
    traefik_dir.mkdir(exist_ok=True)
    generator = src_dir / "ctf_proxy" / "bin" / "traefik-config-gen.py"
    subprocess.run(
        [sys.executable, str(generator), str(config_path), str(traefik_dir)],
        check=True,
    )
    print("Generated traefik dynamic configuration")


def disable_envoy(compose_path: Path) -> None:
    """Remove the envoy service and any dependencies on it from docker-compose.yml."""
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    with open(compose_path) as f:
        compose_data = yaml.load(f)

    services = compose_data.get("services", {})
    if "envoy" not in services:
        return

    del services["envoy"]

    for service in services.values():
        depends_on = service.get("depends_on")
        if isinstance(depends_on, list) and "envoy" in depends_on:
            depends_on.remove("envoy")
            if not depends_on:
                del service["depends_on"]
        elif isinstance(depends_on, dict) and "envoy" in depends_on:
            del depends_on["envoy"]
            if not depends_on:
                del service["depends_on"]

    with open(compose_path, "w") as f:
        yaml.dump(compose_data, f)

    print("Disabled envoy service in docker-compose.yml")


def compose_up(src_dir: Path) -> None:
    """Bring the docker compose stack up."""
    print("Starting services with docker compose...")
    subprocess.run(
        ["docker", "compose", "up", "-d", "--build"],
        cwd=src_dir,
        check=True,
    )


def compose_down(src_dir: Path) -> None:
    """Tear the docker compose stack down."""
    print("Stopping services with docker compose...")
    subprocess.run(
        ["docker", "compose", "down"],
        cwd=src_dir,
        check=True,
    )


def start_command(enable_envoy: bool) -> None:
    """Execute the start command."""
    project_root = Path(__file__).parent.parent.parent
    src_dir = project_root / "src"
    config_path = src_dir / "data" / "config.yml"
    template_path = src_dir / "docker-compose.template.yml"
    compose_path = src_dir / "docker-compose.yml"

    if not config_path.exists():
        print(f"Error: Config file not found at {config_path}")
        return

    config = read_config(config_path)
    print(f"Read config from {config_path}")

    generate_traefik_config(src_dir, config_path)
    ensure_docker_compose(template_path, compose_path)
    if enable_envoy:
        update_docker_compose_with_mounts(compose_path, config)
    else:
        disable_envoy(compose_path)
    compose_up(src_dir)

    print("Start command completed successfully")


def stop_command() -> None:
    """Execute the stop command."""
    project_root = Path(__file__).parent.parent.parent
    src_dir = project_root / "src"
    compose_path = src_dir / "docker-compose.yml"

    if not compose_path.exists():
        print(f"Error: docker-compose.yml not found at {compose_path}")
        return

    compose_down(src_dir)
    print("Stop command completed successfully")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="CTF Proxy Control Panel")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    start_parser = subparsers.add_parser("start", help="Start the CTF proxy services")
    start_parser.add_argument(
        "--envoy", action="store_true", help="Also start the envoy proxy (disabled by default)"
    )
    subparsers.add_parser("stop", help="Stop the CTF proxy services")

    args = parser.parse_args()

    if args.command == "start":
        start_command(args.envoy)
    elif args.command == "stop":
        stop_command()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
