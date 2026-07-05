#!/usr/bin/env python3

import argparse
from pathlib import Path

import uvicorn

from ctf_proxy.dashboard.app import app, init_app


def main():
    parser = argparse.ArgumentParser(description="CTF Proxy Dashboard API Server")
    parser.add_argument(
        "--config",
        default="config.yml",
        help="Path to configuration file (default: config.yml)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind to (default: 8080)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes",
    )

    args = parser.parse_args()

    config_path = Path(args.config)

    if not config_path.exists():
        print(f"Error: Configuration file not found: {config_path}")
        return 1

    # Set environment variables for reload mode
    import os

    os.environ["CTF_CONFIG_PATH"] = str(config_path)

    init_app(str(config_path))

    print(f"Starting dashboard API server on {args.host}:{args.port}")
    print(f"Config: {config_path}")

    uvicorn.run(
        "ctf_proxy.dashboard.app:app" if args.reload else app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    exit(main())
