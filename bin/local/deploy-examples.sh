#!/bin/bash
# Deploy all example services onto a fresh VM.
#
# Usage (from repo root or anywhere):
#   bin/local/deploy-examples.sh [ssh_target]
#
#   ssh_target defaults to root@ctf-proxy-test-hetzner
#
# What it does:
#   1. Installs prerequisites on the VM (docker, compose, make, node, yq, jq).
#   2. Copies examples/ to the VM (re-copying any dir that lands empty).
#   3. Builds and starts every faustctf-2024-* service, every saarctf-2025
#      sub-service, and websocket-echo. Prints a pass/fail summary.
#
# Re-runnable: each service is rebuilt from a clean dist_root.
set -uo pipefail

REMOTE_DIR=/root/examples
REMOTE_SELF=/root/deploy-examples.sh
LOGDIR=/root/deploy-logs
REPORT=/root/deploy-report.txt

# ---------------------------------------------------------------------------
# REMOTE MODE: runs on the VM.
# ---------------------------------------------------------------------------
if [ "${1:-}" = "--remote" ]; then
  mkdir -p "$LOGDIR"; : > "$REPORT"
  record() { printf '%-42s %s\n' "$1" "$2" | tee -a "$REPORT"; }

  count_running() { ( cd "$1" && docker compose ps --status running -q 2>/dev/null | wc -l | tr -d ' '; ); }
  count_total()   { ( cd "$1" && docker compose ps -a -q 2>/dev/null | wc -l | tr -d ' '; ); }

  deploy_faust() {
    local dir="$1" name svc cdir
    name="$(basename "$dir")"
    svc="$(grep -m1 '^SERVICE' "$dir/Makefile" | awk '{print $3}')"
    echo "===== $name (SERVICE=$svc) =====" | tee -a "$REPORT"
    ( cd "$dir" && rm -rf dist_root && make install ) >"$LOGDIR/$name.log" 2>&1
    if [ $? -ne 0 ]; then record "$name" "BUILD_FAIL (see $LOGDIR/$name.log)"; return; fi
    cdir="$dir/dist_root/srv/$svc"
    [ -f "$cdir/docker-compose.yml" ] || { record "$name" "NO_COMPOSE ($cdir)"; return; }
    # asm_chat (SERVICE=achat) wants host port 1337, which saarctf blockrope also uses.
    [ "$svc" = "achat" ] && sed -i 's/1337:1337/1338:1337/' "$cdir/docker-compose.yml"
    ( cd "$cdir" && docker compose up -d ) >>"$LOGDIR/$name.log" 2>&1
    if [ $? -ne 0 ]; then record "$name" "UP_FAIL (see $LOGDIR/$name.log)"; return; fi
    sleep 4
    record "$name" "UP ($(count_running "$cdir")/$(count_total "$cdir") running)"
  }

  deploy_compose() {
    local dir="$1" name="$2" log="$3"
    echo "===== $name =====" | tee -a "$REPORT"
    ( cd "$dir" && docker compose up -d --build ) >"$log" 2>&1
    if [ $? -ne 0 ]; then record "$name" "UP_FAIL (see $log)"; return; fi
    sleep 3
    record "$name" "UP ($(count_running "$dir")/$(count_total "$dir") running)"
  }

  echo "########## FAUSTCTF ##########"
  for d in "$REMOTE_DIR"/faustctf-2024-*; do [ -f "$d/Makefile" ] && deploy_faust "$d"; done

  echo "########## SAARCTF ##########"
  for d in "$REMOTE_DIR"/saarctf-2025/*/; do
    [ -f "${d}docker-compose.yml" ] && deploy_compose "${d%/}" "saarctf/$(basename "$d")" "$LOGDIR/saar-$(basename "$d").log"
  done

  echo "########## MISC ##########"
  [ -f "$REMOTE_DIR/websocket-echo/docker-compose.yml" ] && deploy_compose "$REMOTE_DIR/websocket-echo" "websocket-echo" "$LOGDIR/websocket-echo.log"

  echo "########## SUMMARY ##########" | tee -a "$REPORT"
  running=$(docker ps --format '{{.Names}}' | wc -l | tr -d ' ')
  echo "Containers running: $running"
  echo "DEPLOY_COMPLETE"
  exit 0
fi

# ---------------------------------------------------------------------------
# LOCAL MODE: provision the VM, copy examples, run remote deploy.
# ---------------------------------------------------------------------------
TARGET="${1:-root@ctf-proxy-test-hetzner}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLES_DIR="$SCRIPT_DIR/../../examples"
SSHOPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"
SSH="ssh $SSHOPTS"
SCP="scp $SSHOPTS"

say() { echo -e "\033[1;34m[deploy]\033[0m $*"; }

say "Target: $TARGET"

say "Installing prerequisites on VM..."
$SSH "$TARGET" 'export DEBIAN_FRONTEND=noninteractive; \
  apt-get update -qq && \
  apt-get install -y -qq docker.io docker-compose-v2 make jq python3-pip nodejs npm >/dev/null && \
  pip install --break-system-packages -q yq >/dev/null 2>&1; \
  systemctl enable --now docker >/dev/null 2>&1; \
  docker --version && node --version' || { echo "prereq install failed"; exit 1; }

say "Tearing down any existing containers (safe on a fresh VM)..."
$SSH "$TARGET" 'command -v docker >/dev/null 2>&1 && docker ps -aq | xargs -r docker rm -f >/dev/null 2>&1; true'

say "Copying examples/ to $TARGET:$REMOTE_DIR ..."
$SSH "$TARGET" "rm -rf $REMOTE_DIR && mkdir -p $REMOTE_DIR"
tar --exclude='.git' --exclude='.venv' --exclude='node_modules' \
    --exclude='__pycache__' --exclude='.playwright-mcp' --exclude='dist_root' \
    -czf - -C "$EXAMPLES_DIR" . | $SSH "$TARGET" "tar -xzf - -C $REMOTE_DIR"

say "Verifying copy (re-copying any empty service dirs)..."
for d in "$EXAMPLES_DIR"/faustctf-2024-* "$EXAMPLES_DIR"/saarctf-2025 "$EXAMPLES_DIR"/websocket-echo; do
  n="$(basename "$d")"
  remote_count=$($SSH "$TARGET" "ls -A $REMOTE_DIR/$n 2>/dev/null | wc -l" | tr -d ' ')
  if [ "$remote_count" = "0" ]; then
    say "  re-copying $n (was empty)"
    tar --exclude='.git' --exclude='.venv' --exclude='node_modules' \
        --exclude='__pycache__' --exclude='dist_root' \
        -czf - -C "$EXAMPLES_DIR" "$n" | $SSH "$TARGET" "tar -xzf - -C $REMOTE_DIR"
  fi
done

say "Uploading deploy script and running remote deploy (this builds many images, be patient)..."
$SCP -q "${BASH_SOURCE[0]}" "$TARGET:$REMOTE_SELF"
$SSH "$TARGET" "bash $REMOTE_SELF --remote"

say "Done. Full report on VM: $REPORT  (logs: $LOGDIR/)"
