#!/bin/bash
set -Eeuo pipefail

echo 'Creating envoy user (uid 1337)...'
sudo useradd --system --no-create-home --uid 1337 envoy || true

echo 'Creating container dirs...'
sudo mkdir -p logs/tap logs/pre-tap logs/post-tap logs-archive data
sudo chown -R 1337:1337 logs logs-archive data

# Check if ~/config.yml exists, if not - create using config gen
if [ ! -f ~/config.yml ]; then
    echo 'Generating initial config.yml...'
    python3 ./ctf_proxy/bin/docker-config-gen.py ~/config.yml
else
    echo 'Using existing config.yml...'
fi

sudo cp ~/config.yml data/config.yml

echo 'Setting up iptables rules for proxying...'
sudo PORTS_FILE=data/config.yml python3 ./ctf_proxy/bin/iptables-config.py setup

# echo 'Generating envoy config...'
# sudo python3 ./ctf_proxy/bin/proxy-gen.py -i data/config.yml -o data/envoy.yaml

# run all services
echo 'Starting all services...'
docker-compose up -d --build --force-recreate
