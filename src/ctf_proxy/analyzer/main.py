#!/usr/bin/env python3

import argparse
import os

import uvicorn

from ctf_proxy.analyzer.api import app, init_app


def main():
    parser = argparse.ArgumentParser(description="CTF Proxy Analyzer API Server")
    parser.add_argument("--source-db", default="proxy_stats.db", help="Path to source database")
    parser.add_argument("--analysis-db", default="analysis.db", help="Path to analysis database")
    parser.add_argument("--rules-folder", default="analyzer-rules", help="Rules folder")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8090, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()

    os.environ["SOURCE_DB_FILE"] = args.source_db
    os.environ["ANALYSIS_DB_FILE"] = args.analysis_db
    os.environ["RULES_FOLDER"] = args.rules_folder
    init_app(args.source_db, args.rules_folder, args.analysis_db)

    print(f"Starting analyzer API server on {args.host}:{args.port}")
    print(f"Source database: {args.source_db}")
    print(f"Rules folder: {args.rules_folder}")

    uvicorn.run(
        "ctf_proxy.analyzer.api:app" if args.reload else app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    raise SystemExit(main())
