#!/usr/bin/env bash
# ShopVerse VM bootstrap — Ubuntu 22.04/24.04. Idempotent; run as a sudo-capable user.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/bhatt-neel-dev/shopverse.git}"
APP_DIR="${APP_DIR:-$HOME/shopverse}"

echo "==> Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi

echo "==> Host telemetry (Phase A: SNMP + syslog forward to the appliance)"
sudo apt-get update -qq
sudo apt-get install -y -qq snmpd git curl
# SNMP v2c read-only, community 'shopverse'. Ubuntu ships snmpd bound to 127.0.0.1, which
# makes it invisible to the appliance — agentaddress must cover all interfaces.
sudo tee /etc/snmp/snmpd.conf >/dev/null <<'EOF'
agentaddress udp:161,udp6:[::1]:161
rocommunity shopverse default
rocommunity6 shopverse default
sysLocation ShopVerse Lab
sysContact ops@shopverse.local
sysServices 72
# expose the full tree, not just the default system subset
view   all          included   .1
access notConfigGroup ""  any       noauth    exact  all    none   none
EOF
sudo systemctl enable --now snmpd && sudo systemctl restart snmpd

if [ -n "${APPLIANCE_IP:-}" ]; then
  echo "*.* @${APPLIANCE_IP}:514" | sudo tee /etc/rsyslog.d/90-shopverse.conf >/dev/null
  sudo systemctl restart rsyslog
  echo "syslog forwarding -> ${APPLIANCE_IP}:514"
else
  echo "APPLIANCE_IP not set — skipping syslog forwarding (set it and re-run)"
fi

echo "==> Code"
if [ -d "$APP_DIR/.git" ]; then git -C "$APP_DIR" pull --ff-only; else git clone "$REPO_URL" "$APP_DIR"; fi

echo "==> Stack"
cd "$APP_DIR/deploy"
sudo docker compose up -d --build

echo "==> Done. Storefront :3000 | Scenario Studio :9001 | Gateway :8080 | Locust :8089 | RabbitMQ :15672"
