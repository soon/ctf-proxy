#!/usr/bin/env python3

import sys

import yaml


def generate_docker_compose(config_path: str, template_path: str, output_path: str) -> None:
    with open(config_path) as f:
        config = yaml.safe_load(f)

    with open(template_path) as f:
        docker_compose = yaml.safe_load(f)

    services_with_mount = [s for s in config.get("services", []) if s.get("mount_folder")]

    if services_with_mount:
        volumes = []
        for service in services_with_mount:
            mount_folder = service["mount_folder"]
            mount_name = service["name"].replace("-", "_")
            volumes.append(f"{mount_folder}:/workspace/{mount_name}")

        if "code-server" in docker_compose["services"]:
            docker_compose["services"]["code-server"]["volumes"] = volumes

    with open(output_path, "w") as f:
        yaml.dump(docker_compose, f, sort_keys=False, default_flow_style=False)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: docker-compose-gen.py <config.yml> <template.yml> <output.yml>")
        sys.exit(1)

    generate_docker_compose(sys.argv[1], sys.argv[2], sys.argv[3])
