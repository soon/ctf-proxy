#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UTM_SCRIPT="$SCRIPT_DIR/utm-snapshot.sh"

if [ ! -f "$UTM_SCRIPT" ]; then
    echo "Error: utm-snapshot.sh not found"
    exit 1
fi

if [ $# -eq 0 ]; then
    echo "Available VMs:"
    ls -d ~/Library/Containers/com.utmapp.UTM/Data/Documents/*.utm 2>/dev/null | while read vm; do
        basename "$vm" .utm | sed 's/^/  /'
    done
    echo
    echo "Usage: $0 VM_NAME [ACTION] [SNAPSHOT_NAME]"
    echo "Actions: create (default), delete, restore, list"
    echo "For create: snapshot name is optional (uses timestamp)"
    exit 1
fi

exec "$UTM_SCRIPT" "$@"
