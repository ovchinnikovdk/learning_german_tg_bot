#!/usr/bin/env bash
# Deploy german_learning_bot to raspi5wifi.lan
set -euo pipefail

REMOTE="raspi5wifi.lan"
REMOTE_USER="${REMOTE_USER:-$(whoami)}"
REMOTE_DIR="/home/${REMOTE_USER}/projects/german_learning_bot"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Syncing files to ${REMOTE_USER}@${REMOTE}:${REMOTE_DIR}"
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'data/db.json' --exclude 'data/db_backup.json' \
  "${LOCAL_DIR}/" "${REMOTE_USER}@${REMOTE}:${REMOTE_DIR}/"

echo "==> Installing dependencies on remote"
ssh "${REMOTE_USER}@${REMOTE}" bash <<EOF
  cd "${REMOTE_DIR}"
  python3 -m venv .venv 2>/dev/null || true
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
EOF

echo "==> Installing systemd service"
ssh "${REMOTE_USER}@${REMOTE}" bash <<ENDSSH
set -e
sudo tee "/etc/systemd/system/german-bot.service" > /dev/null <<SERVICE
[Unit]
Description=German Learning Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
User=${REMOTE_USER}
WorkingDirectory=${REMOTE_DIR}
EnvironmentFile=${REMOTE_DIR}/.env
ExecStart=${REMOTE_DIR}/.venv/bin/python -m bot.main
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable german-bot
echo "Service installed. Start with: sudo systemctl start german-bot"
ENDSSH

echo ""
echo "Done! Next steps on the Pi:"
echo "  1. Create ${REMOTE_DIR}/.env with TELEGRAM_BOT_TOKEN=<your_token>"
echo "  2. sudo systemctl start german-bot"
echo "  3. sudo journalctl -fu german-bot   # to watch logs"
