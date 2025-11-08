#!/usr/bin/env python3

import sys

import yaml


def generate_traefik_config(config_path: str, output_dir: str) -> None:
    with open(config_path) as f:
        config = yaml.safe_load(f)

    token = config.get("api_token_hash", "")

    traefik_config = {
        "http": {
            "routers": {
                "code-server": {
                    "rule": "PathPrefix(`/code-server`)",
                    "service": "code-server",
                    "middlewares": ["cookie-token-auth", "code-server-strip"],
                },
                "dashboard-backend": {
                    "rule": "PathPrefix(`/api`)",
                    "service": "dashboard-backend",
                    "middlewares": ["header-token-auth"],
                },
                "dashboard-ui": {
                    "rule": "PathPrefix(`/`)",
                    "service": "dashboard-ui",
                },
            },
            "services": {
                "dashboard-backend": {
                    "loadBalancer": {"servers": [{"url": "http://dashboard-backend:8080"}]}
                },
                "dashboard-ui": {"loadBalancer": {"servers": [{"url": "http://dashboard-ui:80"}]}},
                "code-server": {"loadBalancer": {"servers": [{"url": "http://code-server:3000"}]}},
            },
            "middlewares": {
                "code-server-strip": {
                    "stripPrefix": {
                        "prefixes": ["/code-server"],
                    }
                },
                "header-token-auth": {
                    "plugin": {
                        "auth": {
                            "mode": "header",
                            "tokenSHA256": token,
                        }
                    }
                },
                "cookie-token-auth": {
                    "plugin": {
                        "auth": {
                            "mode": "cookie",
                            "tokenSHA256": token,
                            "cookiePath": "/code-server",
                        }
                    }
                },
            },
        }
    }

    with open(f"{output_dir}/dynamic.yml", "w") as f:
        yaml.dump(traefik_config, f, sort_keys=False)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: traefik-config-gen.py <config.yml> <output_dir>")
        sys.exit(1)

    generate_traefik_config(sys.argv[1], sys.argv[2])
