#!/usr/bin/env bash

set -Eeuo pipefail

echo 'Creating ctf-proxy user...'
useradd -m ctf-proxy

pw=$(openssl rand -base64 32)
echo "ctf-proxy:$pw" | sudo chpasswd && printf "New password for ctf-proxy: %s\n" "$pw"

usermod -aG docker ctf-proxy
echo 'ctf-proxy ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/ctf-proxy

echo 'Setting up SSH for ctf-proxy user...'
mkdir -p /home/ctf-proxy/.ssh
cp ~/.ssh/authorized_keys /home/ctf-proxy/.ssh/authorized_keys
chown -R ctf-proxy:ctf-proxy /home/ctf-proxy/.ssh
chmod 700 /home/ctf-proxy/.ssh
chmod 600 /home/ctf-proxy/.ssh/authorized_keys

usermod -s /bin/bash ctf-proxy

echo 'Installing proxy...'
su - ctf-proxy
cd ~
git clone https://github.com/soon/ctf-proxy.git
cd ctf-proxy/src
make

echo 'Setup complete! You can now login as ctf-proxy user.'
