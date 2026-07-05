#!/bin/bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../src"

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
