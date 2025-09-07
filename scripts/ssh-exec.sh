#!/bin/bash

# SSH Command Executor for utm-ubuntu-vm
# Usage: ./ssh-exec.sh "command to execute"
# Example: ./ssh-exec.sh "ls -la"

set -euo pipefail

# SSH connection details
SSH_USER="q"
SSH_HOST="utm-ubuntu-vm"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
log() {
    local level=$1
    shift
    case $level in
        "ERROR")
            echo -e "${RED}[ERROR]${NC} $*" >&2
            ;;
        "SUCCESS")
            echo -e "${GREEN}[SUCCESS]${NC} $*"
            ;;
        "INFO")
            echo -e "${BLUE}[INFO]${NC} $*"
            ;;
        "WARN")
            echo -e "${YELLOW}[WARN]${NC} $*"
            ;;
    esac
}

# Function to execute SSH command
ssh_exec() {
    local command="$1"
    
    log "INFO" "Executing on ${SSH_USER}@${SSH_HOST}: ${command}"
    
    # Execute the command via SSH
    ssh -o ConnectTimeout=10 \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        "${SSH_USER}@${SSH_HOST}" \
        "${command}"
}

# Function to check SSH connectivity
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

# Function to show usage
usage() {
    echo "Usage: $0 [OPTIONS] <command>"
    echo ""
    echo "Execute commands on remote SSH host ${SSH_USER}@${SSH_HOST}"
    echo ""
    echo "Options:"
    echo "  -c, --check     Check SSH connectivity"
    echo "  -i, --interactive   Start interactive SSH session"
    echo "  -h, --help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 'ls -la'"
    echo "  $0 'ps aux | grep nginx'"
    echo "  $0 'sudo systemctl status docker'"
    echo "  $0 --check"
    echo "  $0 --interactive"
}

# Main script logic
main() {
    # Handle no arguments
    if [ $# -eq 0 ]; then
        usage
        exit 1
    fi
    
    # Parse arguments
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -c|--check)
            check_connection
            exit $?
            ;;
        -i|--interactive)
            log "INFO" "Starting interactive SSH session to ${SSH_USER}@${SSH_HOST}"
            exec ssh -o StrictHostKeyChecking=no \
                     -o UserKnownHostsFile=/dev/null \
                     "${SSH_USER}@${SSH_HOST}"
            ;;
        -*)
            log "ERROR" "Unknown option: $1"
            usage
            exit 1
            ;;
        *)
            # Execute the command
            if ! check_connection; then
                log "ERROR" "Cannot execute command: SSH connection failed"
                exit 1
            fi
            
            ssh_exec "$1"
            exit $?
            ;;
    esac
}

# Run main function with all arguments
main "$@"
