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

echo 'Generating Traefik and docker-compose configs...'
python3 ./ctf_proxy/bin/traefik-config-gen.py ./data/config.yml ./traefik
python3 ./ctf_proxy/bin/docker-compose-gen.py ./data/config.yml ./docker-compose.template.yml ./docker-compose.yml

echo 'Setting ownership for container directories...'
sudo chown -R 1337:1337 logs logs-archive data

echo 'Setting up iptables rules for proxying...'
sudo PORTS_FILE=data/config.yml python3 ./ctf_proxy/bin/iptables-config.py setup

echo 'Building interceptor...'
sudo make -C ./interceptor build LABEL=setup
sudo chown -R $(whoami):$(whoami) ./interceptor/wasm

echo 'Refreshing Envoy config with latest WASM files...'
./ctf_proxy/bin/refresh-envoy.sh

echo 'Starting all services...'
docker-compose up -d --build --force-recreate
