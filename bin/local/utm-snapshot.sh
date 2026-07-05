#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

UTM_DIR="$HOME/Library/Containers/com.utmapp.UTM/Data/Documents"

create_snapshot() {
    local qcow2_file=$1
    local snapshot_name=$2
    qemu-img snapshot -c "$snapshot_name" "$qcow2_file"
}

delete_snapshot() {
    local qcow2_file=$1
    local snapshot_name=$2
    qemu-img snapshot -d "$snapshot_name" "$qcow2_file"
}

restore_snapshot() {
    local qcow2_file=$1
    local snapshot_name=$2
    qemu-img snapshot -a "$snapshot_name" "$qcow2_file"
}

list_snapshots() {
    local qcow2_file=$1
    local snapshots=$(qemu-img info --output=json "$qcow2_file" | jq -r '.snapshots[]? | "\(.id)\t\(.name)\t\(."date-sec" | strftime("%Y-%m-%d %H:%M:%S"))"' 2>/dev/null)
    if [ -n "$snapshots" ]; then
        printf "%-4s %-25s %s\n" "ID" "NAME" "DATE"
        printf "%-4s %-25s %s\n" "--" "----" "----"
        echo "$snapshots" | while IFS=$'\t' read -r id name date; do
            printf "%-4s %-25s %s\n" "$id" "$name" "$date"
        done
    else
        echo "  No snapshots found"
    fi
}

show_usage() {
    cat << EOF
Usage: $0 VM_NAME [ACTION] [SNAPSHOT_NAME]

VM_NAME:       Name of UTM VM
ACTION:        create (default), delete, restore, list
SNAPSHOT_NAME: Snapshot name (optional for create - uses timestamp)

Examples:
    $0 Linux
    $0 Linux create
    $0 Linux create backup-1
    $0 Linux list
    $0 Linux delete backup-1
    $0 Linux restore backup-1
EOF
}

if [ $# -lt 1 ] || [ $# -gt 3 ]; then
    show_usage
    exit 1
fi

VM_NAME="$1"
ACTION="${2:-create}"
SNAPSHOT_NAME="$3"

if [ "$ACTION" = "create" ] && [ -z "$SNAPSHOT_NAME" ]; then
    SNAPSHOT_NAME="snapshot-$(date +%Y%m%d-%H%M%S)"
fi

if [[ ! "$ACTION" =~ ^(create|delete|restore|list)$ ]]; then
    echo -e "${RED}Invalid action: $ACTION${NC}" >&2
    exit 1
fi

if [ ! -d "$UTM_DIR" ]; then
    echo -e "${RED}UTM directory not found${NC}" >&2
    exit 1
fi

if ! command -v qemu-img &> /dev/null; then
    echo -e "${RED}qemu-img not found${NC}" >&2
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo -e "${RED}jq not found${NC}" >&2
    exit 1
fi

vm_path="$UTM_DIR/$VM_NAME.utm"
if [ ! -d "$vm_path" ]; then
    echo -e "${RED}VM '$VM_NAME' not found${NC}" >&2
    exit 1
fi

data_dir="$vm_path/Data"
if [ ! -d "$data_dir" ]; then
    echo -e "${RED}Data directory not found for '$VM_NAME'${NC}" >&2
    exit 1
fi

qcow2_files=()
while IFS= read -r -d '' file; do
    qcow2_files+=("$file")
done < <(find "$data_dir" -name "*.qcow2" -type f -print0)

if [ ${#qcow2_files[@]} -eq 0 ]; then
    echo -e "${RED}No .qcow2 files found for '$VM_NAME'${NC}" >&2
    exit 1
fi

qcow2_file="${qcow2_files[0]}"

if [[ "$ACTION" =~ ^(delete|restore)$ ]] && [ -z "$SNAPSHOT_NAME" ]; then
    echo -e "${RED}Snapshot name required for $ACTION${NC}" >&2
    echo "Available snapshots for '$VM_NAME':"
    list_snapshots "$qcow2_file" 2>/dev/null || echo "  No snapshots found"
    exit 1
fi

case "$ACTION" in
    "create")
        create_snapshot "$qcow2_file" "$SNAPSHOT_NAME"
        echo -e "${GREEN}Created snapshot '$SNAPSHOT_NAME' for '$VM_NAME'${NC}"
        ;;
    "delete")
        delete_snapshot "$qcow2_file" "$SNAPSHOT_NAME"
        echo -e "${GREEN}Deleted snapshot '$SNAPSHOT_NAME' for '$VM_NAME'${NC}"
        ;;
    "restore")
        if ! restore_snapshot "$qcow2_file" "$SNAPSHOT_NAME" 2>/dev/null; then
            echo -e "${RED}Failed to restore snapshot '$SNAPSHOT_NAME'${NC}" >&2
            echo "Available snapshots for '$VM_NAME':"
            list_snapshots "$qcow2_file" 2>/dev/null || echo "  No snapshots found"
            exit 1
        fi
        echo -e "${GREEN}Restored snapshot '$SNAPSHOT_NAME' for '$VM_NAME'${NC}"
        ;;
    "list")
        echo "Snapshots for '$VM_NAME':"
        list_snapshots "$qcow2_file" 2>/dev/null || echo "  No snapshots found"
        ;;
esac
