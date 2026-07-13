#!/bin/bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../src"

echo 'Checking required tools...'
have() { command -v "$1" >/dev/null 2>&1 || [ -x "/usr/sbin/$1" ] || [ -x "/sbin/$1" ]; }
missing=()
for tool in docker python3 make openssl sudo iptables ip6tables ip; do
    have "$tool" || missing+=("$tool")
done
if have docker; then
    docker compose version >/dev/null 2>&1 || missing+=("docker compose plugin (docker-compose-v2 / docker-compose-plugin)")
    docker buildx version  >/dev/null 2>&1 || missing+=("docker buildx plugin (docker-buildx / docker-buildx-plugin)")
fi
if have python3; then
    python3 -c 'import yaml' >/dev/null 2>&1 || missing+=("python3 yaml module (python3-yaml)")
fi
if [ ${#missing[@]} -gt 0 ]; then
    echo "ERROR: required tools are missing:" >&2
    for m in "${missing[@]}"; do echo "  - $m" >&2; done
    echo "Install them and re-run setup. This script does not install dependencies." >&2
    exit 1
fi
echo 'All required tools present.'

echo 'Creating envoy user (uid 1337)...'
sudo useradd --system --no-create-home --uid 1337 envoy || true

echo 'Creating dashboard user (uid 1338)...'
sudo useradd --system --uid 1338 -m dashboard || true

echo 'Creating container dirs...'
mkdir -p logs/tap logs/tcp-tap logs-archive data traefik

echo 'Updating config.yml...'
python3 "$SCRIPT_DIR/config-gen.py" ~/config.yml "$@"
cp ~/config.yml data/config.yml

echo 'Generating Traefik config...'
mkdir -p ./traefik
python3 "$SCRIPT_DIR/traefik-config-gen.py" ./data/config.yml ./traefik

echo 'Generating docker-compose.yml...'
python3 "$SCRIPT_DIR/docker-compose-gen.py" ./data/config.yml ./docker-compose.template.yml ./docker-compose.yml

echo 'Setting ownership for container directories...'
sudo chown -R 1337:1337 logs logs-archive data

echo 'Building interceptor...'
sudo make -C ./envoy/interceptor build LABEL=setup
sudo chown -R $(whoami):$(whoami) ./envoy/interceptor/wasm

echo 'Generating self-signed TLS cert for HTTPS interception (if missing)...'
mkdir -p ./envoy/tls
if [ ! -f ./envoy/tls/cert.pem ] || [ ! -f ./envoy/tls/key.pem ]; then
    openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout ./envoy/tls/key.pem \
        -out ./envoy/tls/cert.pem \
        -days 3650 -subj "/CN=ctf-proxy"
fi
chmod 644 ./envoy/tls/key.pem ./envoy/tls/cert.pem

echo 'Refreshing Envoy config with latest WASM files...'
"$SCRIPT_DIR/refresh-envoy.sh"

echo 'Starting all services...'
docker compose up -d --build --force-recreate

echo 'Seeding analyzer rules into Postgres...'
docker compose exec -T analyzer python -m ctf_proxy.analytics.seed

# must be in the end, so all bridges are known to iptables-config.py
echo 'Setting up iptables rules for proxying...'
sudo PORTS_FILE=data/config.yml python3 "$SCRIPT_DIR/iptables-config.py" setup
