#!/usr/bin/env python3

import json
import subprocess
import sys
from typing import Any


def run_docker_command(args: list[str]) -> str:
    """Run docker command and return output."""
    try:
        result = subprocess.run(["docker"] + args, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running docker command: {e}", file=sys.stderr)
        print(f"stderr: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(
            "Error: Docker not found. Make sure Docker is installed and in PATH.", file=sys.stderr
        )
        sys.exit(1)


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
    if protocol == "udp":
        return "udp"

    common_http_ports = {80, 443, 8000, 8080, 8443, 3000, 5000, 9000}
    websocket_indicators = ["ws", "websocket", "socket", "realtime"]

    if port in common_http_ports:
        return "http"

    container_lower = container_name.lower()
    if any(indicator in container_lower for indicator in websocket_indicators):
        return "ws"

    if any(
        indicator in container_lower for indicator in ["web", "http", "api", "frontend", "backend"]
    ):
        return "http"

    return "tcp"


def sanitize_service_name(name: str) -> str:
    """Sanitize container name to be a valid service name."""
    import re

    name = re.sub(r"^[/\-_]+", "", name)
    name = re.sub(r"[^a-zA-Z0-9\-_]", "-", name)
    name = name.strip("-_")

    return name if name else "service"


def generate_config() -> dict[str, Any]:
    """Generate configuration based on running Docker containers."""
    containers = get_running_containers()

    if not containers:
        print("No running containers found.", file=sys.stderr)
        return {"services": []}

    services = []
    used_ports = set()

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

    services.sort(key=lambda s: s["port"])

    return {"services": services}


def main():
    """Main function."""
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print("Usage: python docker-config-gen.py [output_file]")
        print()
        print("Generate CTF proxy configuration based on running Docker containers.")
        print("Only containers with exposed ports are included.")
        print()
        print("If output_file is not specified, configuration is printed to stdout.")
        sys.exit(0)

    config = generate_config()

    if not config["services"]:
        print("No services with exposed ports found.", file=sys.stderr)
        sys.exit(1)

    yaml_output = "# CTF Proxy Configuration\n"
    yaml_output += "# Generated from running Docker containers\n\n"
    yaml_output += 'flag_format: "FLAG_[A-Za-z0-9/+]{32}"\n\n'
    yaml_output += "services:\n"

    for service in config["services"]:
        yaml_output += f"  - name: {service['name']}\n"
        yaml_output += f"    port: {service['port']}\n"
        yaml_output += f"    type: {service['type']}\n"
        yaml_output += "\n"

    if len(sys.argv) > 1:
        output_file = sys.argv[1]
        try:
            with open(output_file, "w") as f:
                f.write(yaml_output)
            print(f"Configuration written to {output_file}")
        except Exception as e:
            print(f"Error writing to file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(yaml_output, end="")


if __name__ == "__main__":
    main()
