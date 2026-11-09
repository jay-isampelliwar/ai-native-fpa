#!/usr/bin/env bash
# One-time setup for a fresh Debian 12 e2-micro VM: Docker, Compose and 2 GB of swap.
# Run on the VM:  bash setup-vm.sh   then log out and back in so the docker group applies.

set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi

sudo usermod -aG docker "$USER"

if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
fi

echo "vm.swappiness=10" | sudo tee /etc/sysctl.d/99-swappiness.conf >/dev/null
sudo sysctl --system >/dev/null

docker --version
docker compose version
free -h
