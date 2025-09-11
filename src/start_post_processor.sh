#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${1:-/var/log/envoy/http_access.log}"
DB_FILE="${2:-$SCRIPT_DIR/proxy_stats.db}"

echo "Starting CTF Proxy Post-Processor..."
echo "Log file: $LOG_FILE"
echo "Database: $DB_FILE"
echo "Press Ctrl+C to stop"
echo

python3 "$SCRIPT_DIR/post_processor.py" "$LOG_FILE" "$DB_FILE"
