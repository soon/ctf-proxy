#!/usr/bin/env bash
set -euo pipefail

# ===== Config (override via env) =====
PORT="${PORT:-3000}"                  # App's published host port
ENVOY_PORT="${ENVOY_PORT:-15001}"     # Envoy listener on the host
ENVOY_UID="${ENVOY_UID:-1337}"        # UID Envoy runs as
BRIDGE_IFS="${BRIDGE_IFS:-auto}"      # space-separated list or "auto" to detect (docker0, docker_gwbridge, br-*)
PROTECT_ENVOY_PORT="${PROTECT_ENVOY_PORT:-1}"  # Drop direct remote hits to ENVOY_PORT
ENABLE_IPV6="${ENABLE_IPV6:-auto}"    # auto|1|0

IPT="${IPT:-iptables}"
IP6T="${IP6T:-ip6tables}"
USER_CHAIN="ENVOY_PRE"

need_root() {
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo "This script must run as root (use sudo)." >&2
    exit 1
  fi
}

have_cmd() { command -v "$1" >/dev/null 2>&1; }

ipv6_wanted() {
  case "${ENABLE_IPV6,,}" in
    1|true|yes) return 0 ;;
    0|false|no) return 1 ;;
    *) have_cmd "$IP6T" ;;  # auto: enable if ip6tables exists
  esac
}

# ---- Helpers (use $IPT set in the caller) ----
rule_exists() { local table=$1 chain=$2; shift 2; $IPT -t "$table" -C "$chain" "$@" >/dev/null 2>&1; }
chain_exists(){ $IPT -t "$1" -nL "$2" >/dev/null 2>&1; }
ensure_chain(){ chain_exists "$1" "$2" || $IPT -t "$1" -N "$2"; }
delete_chain_if_empty(){ chain_exists "$1" "$2" && { $IPT -t "$1" -F "$2" || true; $IPT -t "$1" -X "$2" || true; }; }
add_rule_top(){ local table=$1 chain=$2; shift 2; rule_exists "$table" "$chain" "$@" || $IPT -t "$table" -I "$chain" 1 "$@"; }
add_rule_end(){ local table=$1 chain=$2; shift 2; rule_exists "$table" "$chain" "$@" || $IPT -t "$table" -A "$chain" "$@"; }
del_rule(){ local table=$1 chain=$2; shift 2; rule_exists "$table" "$chain" "$@" && $IPT -t "$table" -D "$chain" "$@"; }

detect_bridges() {
  local ifs
  mapfile -t ifs < <(ip -o link show type bridge 2>/dev/null | awk -F': ' '{print $2}' | \
                     grep -E '^(docker0|docker_gwbridge|br-.*)$' || true)
  printf "%s" "${ifs[*]:-}"
}

setup_family() { # $1=iptables cmd (iptables or ip6tables)  $2=label
  local IPT="$1" label="$2"
  echo "[+] (${label}) Setting up NAT redirects for port $PORT via Envoy :$ENVOY_PORT (UID $ENVOY_UID)"

  ensure_chain nat "$USER_CHAIN"
  add_rule_top nat PREROUTING -p tcp --dport "$PORT" -m comment --comment "envoy: jump to $USER_CHAIN" -j "$USER_CHAIN"

  # Rebuild user chain rules
  $IPT -t nat -F "$USER_CHAIN"

  # Skip docker bridges
  if [[ -n "${EXCL_IFS}" ]]; then
    for ifname in $EXCL_IFS; do
      add_rule_end nat "$USER_CHAIN" -i "$ifname" -p tcp \
        -m comment --comment "envoy: skip on $ifname" -j RETURN
    done
  fi

  # Final redirect
  add_rule_end nat "$USER_CHAIN" -p tcp \
    -m comment --comment "envoy: redirect to $ENVOY_PORT" \
    -j REDIRECT --to-ports "$ENVOY_PORT"

  # Local OUTPUT redirect (exclude Envoy itself)
  add_rule_top nat OUTPUT -p tcp --dport "$PORT" -m addrtype --dst-type LOCAL \
    -m owner ! --uid-owner "$ENVOY_UID" \
    -m comment --comment "envoy: local redirect to $ENVOY_PORT" \
    -j REDIRECT --to-ports "$ENVOY_PORT"

  # Optional: protect Envoy listener
  if [[ "$PROTECT_ENVOY_PORT" == "1" ]]; then
    add_rule_top raw PREROUTING ! -i lo -p tcp --dport "$ENVOY_PORT" \
      -m comment --comment "envoy: drop direct hits to $ENVOY_PORT" -j DROP
  fi
  echo "[✓] (${label}) Setup complete."
}

teardown_family() { # $1=iptables cmd  $2=label
  local IPT="$1" label="$2"
  echo "[+] (${label}) Tearing down NAT redirects for port $PORT"

  del_rule nat PREROUTING -p tcp --dport "$PORT" -m comment --comment "envoy: jump to $USER_CHAIN" -j "$USER_CHAIN"
  delete_chain_if_empty nat "$USER_CHAIN"

  del_rule nat OUTPUT -p tcp --dport "$PORT" -m addrtype --dst-type LOCAL \
    -m owner ! --uid-owner "$ENVOY_UID" \
    -m comment --comment "envoy: local redirect to $ENVOY_PORT" \
    -j REDIRECT --to-ports "$ENVOY_PORT"

  if [[ "$PROTECT_ENVOY_PORT" == "1" ]]; then
    del_rule raw PREROUTING ! -i lo -p tcp --dport "$ENVOY_PORT" \
      -m comment --comment "envoy: drop direct hits to $ENVOY_PORT" -j DROP
  fi
  echo "[✓] (${label}) Teardown complete."
}

setup() {
  # Resolve bridges once (used for v4 and v6)
  if [[ "${BRIDGE_IFS,,}" == "auto" || -z "${BRIDGE_IFS}" ]]; then
    EXCL_IFS="$(detect_bridges)"
  else
    EXCL_IFS="$BRIDGE_IFS"
  fi
  echo "[i] Excluding bridge interfaces from REDIRECT: ${EXCL_IFS:-<none>}"

  setup_family "$IPT" "IPv4"
  if ipv6_wanted; then
    setup_family "$IP6T" "IPv6"
  else
    echo "[i] IPv6 disabled or unavailable; skipping IPv6 rules."
  fi
}

teardown() {
  teardown_family "$IPT" "IPv4"
  if ipv6_wanted; then
    teardown_family "$IP6T" "IPv6"
  fi
}

usage() {
  cat >&2 <<EOF
Usage: sudo $(basename "$0") setup|teardown

Environment overrides:
  PORT=$PORT
  ENVOY_PORT=$ENVOY_PORT
  ENVOY_UID=$ENVOY_UID
  BRIDGE_IFS=$BRIDGE_IFS        # space-separated list or "auto"
  PROTECT_ENVOY_PORT=$PROTECT_ENVOY_PORT
  ENABLE_IPV6=$ENABLE_IPV6      # auto|1|0
  IPT=$IPT
  IP6T=$IP6T

Notes:
  • IPv4 and IPv6 traffic to TCP:\$PORT is redirected to :\$ENVOY_PORT before Docker's DNAT, except on excluded bridges.
  • Local traffic (127.0.0.1 and ::1) is redirected too; Envoy's UID is excluded to avoid loops.
  • Direct remote hits to :\$ENVOY_PORT are dropped (both v4 and v6) when PROTECT_ENVOY_PORT=1.
EOF
  exit 2
}

main() {
  need_root
  case "${1:-}" in
    setup) setup ;;
    teardown) teardown ;;
    *) usage ;;
  esac
}

main "$@"
