#!/usr/bin/env bash
# Deploy german_learning_bot to raspi5wifi.lan via Docker Compose
set -euo pipefail

REMOTE="raspi5wifi.lan"
REMOTE_USER="${REMOTE_USER:-$(whoami)}"
REMOTE_DIR="/home/${REMOTE_USER}/projects/german_learning_bot"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Syncing files to ${REMOTE_USER}@${REMOTE}:${REMOTE_DIR}"
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'data/' --exclude '.venv' --exclude 'venv' \
  "${LOCAL_DIR}/" "${REMOTE_USER}@${REMOTE}:${REMOTE_DIR}/"

echo "==> Rebuilding and restarting via Docker Compose"
ssh "${REMOTE_USER}@${REMOTE}" bash <<EOF
  set -e
  cd "${REMOTE_DIR}"
  docker compose build
  docker compose down --remove-orphans
  docker compose up -d
  echo "Containers running:"
  docker compose ps
EOF

echo ""
echo "Done! Useful commands on the Pi:"
echo "  docker compose -f ${REMOTE_DIR}/docker-compose.yml logs -f"
echo "  docker compose -f ${REMOTE_DIR}/docker-compose.yml ps"
echo "  docker compose -f ${REMOTE_DIR}/docker-compose.yml down"
