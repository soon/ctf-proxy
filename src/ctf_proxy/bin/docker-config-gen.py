#!/usr/bin/env python3

import hashlib
import json
import os
import secrets
import subprocess
import sys
from typing import Any

import yaml


def run_docker_command(args: list[str]) -> str:
    """Run docker command and return output."""
    try:
        result = subprocess.run(["docker"] + args, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running docker command: {e}", file=sys.stderr)
        print(f"stderr: {e.stderr}", file=sys.stderr)
        return ""
    except FileNotFoundError:
        print(
            "Warning: Docker not found. Generating config without Docker container detection.",
            file=sys.stderr,
        )
        return ""


def get_running_containers() -> list[dict[str, Any]]:
    """Get list of running containers with their port mappings."""
    containers_json = run_docker_command(["ps", "--format", "json", "--filter", "status=running"])

    if not containers_json.strip():
        return []

    containers = []
    for line in containers_json.strip().split("\n"):
        if line.strip():
            containers.append(json.loads(line))

    return containers


def parse_port_mappings(ports_str: str) -> list[dict[str, Any]]:
    """Parse Docker port mappings string into structured data."""
    if not ports_str:
        return []

    mappings = []

    for port_mapping in ports_str.split(", "):
        port_mapping = port_mapping.strip()

        if "->" in port_mapping:
            external_part, internal_part = port_mapping.split("->", 1)

            internal_port = internal_part.split("/")[0]
            protocol = internal_part.split("/")[1] if "/" in internal_part else "tcp"

            external_port = external_part.split(":")[-1] if ":" in external_part else external_part

            try:
                mappings.append(
                    {
                        "external_port": int(external_port),
                        "internal_port": int(internal_port),
                        "protocol": protocol,
                    }
                )
            except ValueError:
                continue

    return mappings


def determine_service_type(port: int, protocol: str, container_name: str) -> str:
    """Determine service type based on port, protocol and container name."""
    available_types = {"http", "ws", "tcp", "udp"}
    while True:
        res = (
            input(
                f"Enter service type for container '{container_name}' on port {port}/{protocol} (http [default], ws, tcp, udp): "
            )
            .strip()
            .lower()
        )
        if not res:
            res = "http"
        if res in available_types:
            return res
        print(f"Invalid service type: {res}. Please enter one of: {', '.join(available_types)}")


def sanitize_service_name(name: str) -> str:
    """Sanitize container name to be a valid service name."""
    import re

    name = re.sub(r"^[/\-_]+", "", name)
    name = re.sub(r"[^a-zA-Z0-9\-_]", "-", name)
    name = name.strip("-_")

    return name if name else "service"


def load_existing_config(file_path: str) -> dict[str, Any]:
    """Load existing configuration file if it exists."""
    if not os.path.exists(file_path):
        return {}

    try:
        with open(file_path) as f:
            config = yaml.safe_load(f) or {}
            return config
    except Exception as e:
        print(f"Warning: Failed to load existing config: {e}", file=sys.stderr)
        return {}


def get_existing_ports(config: dict[str, Any]) -> set[int]:
    """Extract all ports from existing configuration."""
    ports = set()
    if "services" in config and isinstance(config["services"], list):
        for service in config["services"]:
            if isinstance(service, dict) and "port" in service:
                ports.add(int(service["port"]))
    return ports


def should_skip_container(container_name: str, port: int) -> bool:
    """Check if container should be skipped from proxy configuration."""
    return port in [48955, 15000, 15001, 15002]


def generate_random_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_hex(length)


def hash_token(token: str) -> str:
    """Create SHA256 hash of token."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_config(existing_config: dict[str, Any] = None) -> dict[str, Any]:
    """Generate configuration based on running Docker containers, merging with existing config."""
    containers = get_running_containers()

    if not containers:
        print("No running containers found.", file=sys.stderr)
        if existing_config:
            return existing_config
        return {"services": []}

    # Get existing services and their ports
    if existing_config is None:
        existing_config = {}

    existing_ports = get_existing_ports(existing_config)
    existing_services = existing_config.get("services", [])

    # Start with existing services
    services = list(existing_services)
    used_ports = existing_ports.copy()

    new_services_count = 0
    skipped_count = 0

    for container in containers:
        container_name = container.get("Names", "")
        ports_str = container.get("Ports", "")

        if not ports_str:
            continue

        port_mappings = parse_port_mappings(ports_str)

        if not port_mappings:
            continue

        service_name = sanitize_service_name(container_name)

        for i, mapping in enumerate(port_mappings):
            external_port = mapping["external_port"]
            protocol = mapping["protocol"]

            # Skip proxy infrastructure containers and ports
            if should_skip_container(container_name, external_port):
                skipped_count += 1
                print(f"Skipping infrastructure service on port {external_port}", file=sys.stderr)
                continue

            # Skip if port already exists in configuration
            if external_port in used_ports:
                continue

            used_ports.add(external_port)

            final_service_name = service_name
            if i > 0:
                final_service_name = f"{service_name}-{i + 1}"

            service_type = determine_service_type(external_port, protocol, container_name)

            services.append(
                {"name": final_service_name, "port": external_port, "type": service_type}
            )
            new_services_count += 1

    if new_services_count > 0:
        print(f"Added {new_services_count} new service(s) to configuration.", file=sys.stderr)
    if skipped_count > 0:
        print(f"Skipped {skipped_count} proxy infrastructure service(s).", file=sys.stderr)
    if new_services_count == 0 and skipped_count == 0:
        print("No new services to add (all ports already configured).", file=sys.stderr)

    services.sort(key=lambda s: s["port"])

    # Preserve other config fields from existing config
    result = existing_config.copy()
    result["services"] = services

    # Add default flag_format if not present
    if "flag_format" not in result:
        result["flag_format"] = "FLAG_[A-Za-z0-9/+]{32}"

    # Add default API token hash if not present
    if "api_token_hash" not in result:
        api_token = generate_random_token()
        result["api_token_hash"] = hash_token(api_token)
        print(f"Generated new API token: {api_token}", file=sys.stderr)
        print(f"Token hash: {result['api_token_hash']}", file=sys.stderr)
        print("IMPORTANT: Save this token securely as it will not be shown again!", file=sys.stderr)

    return result


def save_config(config: dict[str, Any], filename: str) -> str:
    """Convert configuration dictionary to YAML string."""
    with open(filename, "w") as f:
        f.write("# CTF Proxy Configuration\n")
        f.write("# Generated/Updated from running Docker containers\n\n")
        yaml.dump(config, f, sort_keys=False)


def main():
    """Main function."""
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print("Usage: python docker-config-gen.py [output_file]")
        print()
        print("Generate/Update CTF proxy configuration based on running Docker containers.")
        print("Only containers with exposed ports are included.")
        print()
        print("If output_file is specified and exists, new services will be merged.")
        print("If output_file is not specified, configuration is printed to stdout.")
        print()
        print("Existing services (matched by port) are preserved.")
        sys.exit(0)

    # Load existing config if output file is specified and exists
    existing_config = {}
    if len(sys.argv) > 1:
        output_file = sys.argv[1]
        existing_config = load_existing_config(output_file)
        if existing_config:
            print(f"Loaded existing configuration from {output_file}", file=sys.stderr)

    config = generate_config(existing_config)

    if not config.get("services"):
        print("No services found in configuration.", file=sys.stderr)
        # Create empty services list - this is normal during setup or when no containers are running
        config["services"] = []

    save_config(config, output_file if len(sys.argv) > 1 else "/dev/stdout")


if __name__ == "__main__":
    main()
