#!/usr/bin/env python3

import sys

import yaml


def generate_traefik_config(config_path: str, output_dir: str) -> None:
    with open(config_path) as f:
        config = yaml.safe_load(f)

    services_with_mount = [s for s in config.get("services", []) if s.get("mount_folder")]

    traefik_config = {
        "http": {
            "routers": {
                "code-server": {
                    "rule": "PathPrefix(`/code-server`)",
                    "service": "code-server",
                    "middlewares": ["code-server-strip"],
                    "priority": 90,
                },
                "api": {
                    "rule": "PathPrefix(`/api`)",
                    "service": "dashboard-backend",
                    "priority": 80,
                },
                "frontend": {
                    "rule": "PathPrefix(`/`)",
                    "service": "frontend",
                    "priority": 1,
                },
            },
            "services": {
                "dashboard-backend": {
                    "loadBalancer": {"servers": [{"url": "http://dashboard-backend:48956"}]}
                },
                "code-server": {"loadBalancer": {"servers": [{"url": "http://code-server:3000"}]}},
                "frontend": {"loadBalancer": {"servers": [{"url": "http://frontend:80"}]}},
            },
            "middlewares": {
                "code-server-strip": {
                    "stripPrefix": {
                        "prefixes": ["/code-server"],
                        "forceSlash": False,
                    }
                },
            },
        }
    }

    with open(f"{output_dir}/dynamic.yml", "w") as f:
        yaml.dump(traefik_config, f, sort_keys=False)

    mount_volumes = []
    for service in services_with_mount:
        mount_folder = service["mount_folder"]
        mount_name = service["name"].replace("-", "_")
        mount_volumes.append(f"      - {mount_folder}:/workspace/{mount_name}")

    print("\n".join(mount_volumes), file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: traefik-config-gen.py <config.yml> <output_dir>")
        sys.exit(1)

    generate_traefik_config(sys.argv[1], sys.argv[2])
