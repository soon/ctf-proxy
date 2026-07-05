#!/usr/bin/env python3

import argparse

import uvicorn

from ctf_proxy.analytics.api import app, init_app
from ctf_proxy.db import connection


def main():
    parser = argparse.ArgumentParser(description="CTF Proxy Analyzer API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8090, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()

    init_app()

    print(f"Starting analyzer API server on {args.host}:{args.port}")
    print(f"Database: {connection.describe()}")

    uvicorn.run(
        "ctf_proxy.analytics.api:app" if args.reload else app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    raise SystemExit(main())
