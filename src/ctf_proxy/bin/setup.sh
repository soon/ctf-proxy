#!/bin/bash
set -Eeuo pipefail

echo 'Creating envoy user (uid 1337)...'
sudo useradd --system --no-create-home --uid 1337 envoy || true

echo 'Creating dashboard user (uid 1338)...'
sudo useradd --system --uid 1338 -m dashboard || true

echo 'Creating container dirs...'
mkdir -p logs/tap logs/tcp-tap logs-archive data traefik

echo 'Updating config.yml...'
python3 ./ctf_proxy/bin/config-gen.py ~/config.yml "$@"
cp ~/config.yml data/config.yml

echo 'Generating Traefik config...'
mkdir -p ./traefik
python3 ./ctf_proxy/bin/traefik-config-gen.py ./data/config.yml ./traefik

echo 'Generating docker-compose.yml...'
python3 ./ctf_proxy/bin/docker-compose-gen.py ./data/config.yml ./docker-compose.template.yml ./docker-compose.yml

echo 'Setting ownership for container directories...'
sudo chown -R 1337:1337 logs logs-archive data

echo 'Building interceptor...'
sudo make -C ./interceptor build LABEL=setup
sudo chown -R $(whoami):$(whoami) ./interceptor/wasm

echo 'Generating self-signed TLS cert for HTTPS interception (if missing)...'
mkdir -p ./ctf_proxy/proxy/tls
if [ ! -f ./ctf_proxy/proxy/tls/cert.pem ] || [ ! -f ./ctf_proxy/proxy/tls/key.pem ]; then
    openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout ./ctf_proxy/proxy/tls/key.pem \
        -out ./ctf_proxy/proxy/tls/cert.pem \
        -days 3650 -subj "/CN=ctf-proxy"
fi
chmod 644 ./ctf_proxy/proxy/tls/key.pem ./ctf_proxy/proxy/tls/cert.pem

echo 'Refreshing Envoy config with latest WASM files...'
./ctf_proxy/bin/refresh-envoy.sh

echo 'Starting all services...'
docker compose up -d --build --force-recreate

# must be in the end, so all bridges are known to iptables-config.py
echo 'Setting up iptables rules for proxying...'
sudo PORTS_FILE=data/config.yml python3 ./ctf_proxy/bin/iptables-config.py setup
