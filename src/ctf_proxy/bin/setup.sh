#!/bin/bash
set -Eeuo pipefail

echo 'Creating envoy user (uid 1337)...'
sudo useradd --system --no-create-home --uid 1337 envoy || true

echo 'Creating dashboard user (uid 1338)...'
sudo useradd --system --uid 1338 -m dashboard || true

echo 'Creating container dirs...'
sudo mkdir -p logs/tap logs/tcp-tap logs-archive data

echo 'Updating config.yml...'
python3 ./ctf_proxy/bin/docker-config-gen.py ~/config.yml
sudo cp ~/config.yml data/config.yml

sudo chown -R 1337:1337 logs logs-archive data

echo 'Setting up iptables rules for proxying...'
sudo PORTS_FILE=data/config.yml python3 ./ctf_proxy/bin/iptables-config.py setup

echo 'Building interceptor...'
sudo make -C ./interceptor build LABEL=setup

echo 'Refreshing Envoy config with latest WASM files...'
sudo ./ctf_proxy/bin/refresh-envoy.sh

echo 'Starting all services...'
docker-compose up -d --build --force-recreate
