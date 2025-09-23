#!/usr/bin/env bash

set -Eeuo pipefail
set -x

useradd -m ctf-proxy
passwd ctf-proxy
usermod -aG docker ctf-proxy
echo 'ctf-proxy ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/ctf-proxy
mkdir -p /home/ctf-proxy/.ssh
cp ~/.ssh/authorized_keys /home/ctf-proxy/.ssh/authorized_keys
chown -R ctf-proxy:ctf-proxy /home/ctf-proxy/.ssh
chmod 700 /home/ctf-proxy/.ssh
chmod 600 /home/ctf-proxy/.ssh/authorized_keys
usermod -s /bin/bash ctf-proxy
