#!/usr/bin/env bash
# Provision the codebase indexer on the Hermes VM.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/home/ubuntu/.hermes}"
INDEXER_HOME="${HERMES_HOME}/indexer"
MIRRORS_ROOT="${HERMES_HOME}/mirrors"
PYTHON="${PYTHON:-python3}"

echo "[indexer] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq git python3 python3-pip python3-venv postgresql-client-16

echo "[indexer] Creating indexer directory at ${INDEXER_HOME}..."
mkdir -p "${INDEXER_HOME}"
mkdir -p "${MIRRORS_ROOT}"

echo "[indexer] Setting up Python virtual environment..."
"${PYTHON}" -m venv "${INDEXER_HOME}/venv"
source "${INDEXER_HOME}/venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet psycopg2-binary

echo "[indexer] Installing Hermes indexer package..."
# Install from the repo checkout
if [ -d "/home/ubuntu/hermes" ]; then
    pip install -e /home/ubuntu/hermes
else
    echo "[indexer] WARNING: Hermes repo not found at /home/ubuntu/hermes"
    echo "[indexer] Install manually: pip install -e /path/to/hermes"
fi

echo "[indexer] Creating default config..."
if [ ! -f "${INDEXER_HOME}/config.json" ]; then
    cat > "${INDEXER_HOME}/config.json" << 'CONFIG'
{
    "allowlist": [],
    "mirrors_root": "/home/ubuntu/.hermes/mirrors",
    "webhook_port": 8080,
    "webhook_rate_limit": 60,
    "reconcile_interval_minutes": 60,
    "inactive_days": 14,
    "inactive_pool_gb": 80,
    "db_host": "127.0.0.1",
    "db_port": 5433,
    "db_name": "codebase_index",
    "db_user": "postgres",
    "excluded_paths": [
        ".env", ".env.*", "__pycache__", "*.pyc",
        "node_modules", "vendor", ".git", ".DS_Store",
        "*.min.js", "*.min.css", "dist", "build",
        ".next", "target", "*.generated.*", "*.pb.go", "*.pb.swift"
    ]
}
CONFIG
    echo "[indexer] Created default config at ${INDEXER_HOME}/config.json"
fi

echo "[indexer] Creating systemd service for webhook..."
sudo tee /etc/systemd/system/hermes-indexer-webhook.service > /dev/null << 'SERVICE'
[Unit]
Description=Hermes Codebase Indexer Webhook
After=network.target postgresql@14-main.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/.hermes/indexer
ExecStart=/home/ubuntu/.hermes/indexer/venv/bin/python -m hermes.indexer webhook
Restart=on-failure
RestartSec=10
Environment=INDEXER_CONFIG=/home/ubuntu/.hermes/indexer/config.json

[Install]
WantedBy=multi-user.target
SERVICE

echo "[indexer] Creating systemd timer for reconcile..."
sudo tee /etc/systemd/system/hermes-indexer-reconcile.service > /dev/null << 'SERVICE'
[Unit]
Description=Hermes Codebase Indexer Reconcile

[Service]
Type=oneshot
User=ubuntu
ExecStart=/home/ubuntu/.hermes/indexer/venv/bin/python -m hermes.indexer reconcile --once
Environment=INDEXER_CONFIG=/home/ubuntu/.hermes/indexer/config.json
SERVICE

sudo tee /etc/systemd/system/hermes-indexer-reconcile.timer > /dev/null << 'TIMER'
[Unit]
Description=Hourly codebase indexer reconcile

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
TIMER

echo "[indexer] Applying migrations..."
cd /home/ubuntu/hermes 2>/dev/null || true
if [ -f db/migrate.sh ]; then
    bash db/migrate.sh codebase_index || echo "[indexer] Migration may have already been applied"
fi

echo "[indexer] Provisioning complete."
echo ""
echo "  Config:       ${INDEXER_HOME}/config.json"
echo "  Mirrors:      ${MIRRORS_ROOT}"
echo "  Webhook:      systemctl start hermes-indexer-webhook"
echo "  Reconcile:    systemctl start hermes-indexer-reconcile.timer"
echo ""
echo "  Add an allowlist entry, then run:"
echo "    python -m hermes.indexer first-index owner/repo"
