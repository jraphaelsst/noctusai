#!/usr/bin/env bash
# 01-provision-vps.sh — bootstrap a fresh Ubuntu 24.04 VPS for noctusai-bot.
#
# What this does (idempotent — safe to re-run):
#   1. apt update + install (docker, git, ufw, curl, jq, unzip, cloudflared)
#   2. Enable Docker daemon + add deploy user to docker group
#   3. Configure UFW firewall: deny inbound except SSH (Cloudflare Tunnel
#      handles inbound HTTPS, so no ports 80/443 exposed publicly)
#   4. Create /opt/noctus directory tree for the app
#
# Usage (run AS ROOT on the target VPS):
#   curl -fsSL https://raw.githubusercontent.com/<repo>/.../01-provision-vps.sh | sudo bash
#   OR
#   ssh root@<vps-ip> 'bash -s' < scripts/deploy/01-provision-vps.sh
#
# Exit codes: 0 success, 1 missing prereqs, 2 install failure.

set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-noctus}"
APP_DIR="${APP_DIR:-/opt/noctus}"

echo "==> noctusai-bot VPS provisioning (user=$DEPLOY_USER, app_dir=$APP_DIR)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: must run as root (sudo)." >&2
  exit 1
fi

# ----- 1. APT prereqs -----
echo "==> updating apt + installing baseline packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  ca-certificates curl gnupg lsb-release git ufw jq unzip \
  apt-transport-https software-properties-common

# ----- 2. Docker -----
if ! command -v docker >/dev/null 2>&1; then
  echo "==> installing Docker Engine + Compose plugin"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
else
  echo "==> Docker already installed: $(docker --version)"
fi

# ----- 3. cloudflared -----
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "==> installing cloudflared"
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
  echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared jammy main' \
    > /etc/apt/sources.list.d/cloudflared.list
  apt-get update -qq
  apt-get install -y -qq cloudflared
else
  echo "==> cloudflared already installed: $(cloudflared --version 2>&1 | head -1)"
fi

# ----- 4. Deploy user -----
if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
  echo "==> creating deploy user: $DEPLOY_USER"
  useradd -m -s /bin/bash -G docker "$DEPLOY_USER"
  # Copy root's authorized_keys so the same SSH key works for the deploy user
  if [[ -f /root/.ssh/authorized_keys ]]; then
    mkdir -p "/home/$DEPLOY_USER/.ssh"
    cp /root/.ssh/authorized_keys "/home/$DEPLOY_USER/.ssh/authorized_keys"
    chown -R "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
    chmod 700 "/home/$DEPLOY_USER/.ssh"
    chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
  fi
else
  echo "==> deploy user $DEPLOY_USER already exists"
  # Ensure docker group membership
  usermod -aG docker "$DEPLOY_USER"
fi

# ----- 5. App directory -----
mkdir -p "$APP_DIR"
chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"

# ----- 6. Firewall -----
echo "==> configuring UFW (allow SSH only on host; everything else flows via Cloudflare Tunnel)"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH"
# NOTE: do NOT open 80/443. Cloudflared makes outbound connections to
# Cloudflare's edge and serves HTTPS-via-tunnel; we never need inbound
# HTTP/HTTPS on the VPS itself.
ufw --force enable

# ----- 7. Auto-restart Docker on boot -----
systemctl enable docker

# ----- 8. Summary -----
echo ""
echo "✓ VPS provisioning complete."
echo ""
echo "  Docker:        $(docker --version)"
echo "  Compose:       $(docker compose version --short 2>/dev/null || echo 'plugin installed')"
echo "  cloudflared:   $(cloudflared --version 2>&1 | head -1)"
echo "  Deploy user:   $DEPLOY_USER (with docker group)"
echo "  App directory: $APP_DIR"
echo "  Firewall:      $(ufw status | head -1)"
echo ""
echo "Next:"
echo "  Run 02-deploy-stack.sh as the $DEPLOY_USER user."
