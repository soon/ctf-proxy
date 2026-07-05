#!/bin/bash

# SSH session opener for utm-ubuntu-vm
# Usage: ./ssh-vm.sh            # open an interactive shell on the VM
#        ./ssh-vm.sh -c         # check connectivity, then exit

set -euo pipefail

# SSH connection details
SSH_USER="q"
SSH_HOST="ubuntu-24-04-vm.local"

# Local port forward: localhost:${LOCAL_PORT} -> ${SSH_HOST}:${REMOTE_PORT}
LOCAL_PORT="49955"
REMOTE_PORT="48955"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    local level=$1
    shift
    case $level in
        "ERROR")   echo -e "${RED}[ERROR]${NC} $*" >&2 ;;
        "SUCCESS") echo -e "${GREEN}[SUCCESS]${NC} $*" ;;
        "INFO")    echo -e "${BLUE}[INFO]${NC} $*" ;;
    esac
}

check_connection() {
    log "INFO" "Checking SSH connectivity to ${SSH_USER}@${SSH_HOST}..."
    if ssh -o ConnectTimeout=5 \
           -o StrictHostKeyChecking=no \
           -o UserKnownHostsFile=/dev/null \
           -o LogLevel=ERROR \
           "${SSH_USER}@${SSH_HOST}" \
           "echo 'Connection successful'" >/dev/null 2>&1; then
        log "SUCCESS" "SSH connection established"
        return 0
    else
        log "ERROR" "Failed to establish SSH connection"
        return 1
    fi
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Open an interactive SSH session on ${SSH_USER}@${SSH_HOST}"
    echo "Forwards local port ${LOCAL_PORT} -> ${SSH_HOST}:${REMOTE_PORT}"
    echo ""
    echo "Options:"
    echo "  -c, --check     Check SSH connectivity and exit"
    echo "  -h, --help      Show this help message"
}

main() {
    case ${1:-} in
        -h|--help)
            usage
            exit 0
            ;;
        -c|--check)
            check_connection
            exit $?
            ;;
        "")
            log "INFO" "Opening interactive SSH session to ${SSH_USER}@${SSH_HOST}"
            log "INFO" "Forwarding local ${LOCAL_PORT} -> ${SSH_HOST}:${REMOTE_PORT}"
            exec ssh -o StrictHostKeyChecking=no \
                     -o UserKnownHostsFile=/dev/null \
                     -o LogLevel=ERROR \
                     -L "${LOCAL_PORT}:localhost:${REMOTE_PORT}" \
                     "${SSH_USER}@${SSH_HOST}"
            ;;
        *)
            log "ERROR" "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
}

main "$@"
