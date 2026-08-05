#!/usr/bin/env bash
# Provision the codebase indexer on the Hermes VM.
set -euo pipefail

# XDG defaults (ADR 0007): ~/.hermes belongs to the OFFICIAL hermes-agent.
INDEXER_HOME="${INDEXER_HOME:-$HOME/.local/share/hermes-indexer}"
MIRRORS_ROOT="${MIRRORS_ROOT:-$HOME/.local/share/hermes-indexer/mirrors}"
INDEXER_CONFIG="${INDEXER_CONFIG:-$HOME/.config/hermes-indexer/config.json}"
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
mkdir -p "$(dirname "${INDEXER_CONFIG}")"
if [ ! -f "${INDEXER_CONFIG}" ]; then
    cat > "${INDEXER_CONFIG}" << CONFIG
{
    "allowlist": [],
    "mirrors_root": "$MIRRORS_ROOT",
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
    echo "[indexer] Created default config at ${INDEXER_CONFIG}"
fi

echo "[indexer] Creating systemd service for webhook..."
sudo tee /etc/systemd/system/hermes-indexer-webhook.service > /dev/null << SERVICE
[Unit]
Description=Hermes Codebase Indexer Webhook
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$INDEXER_HOME
ExecStart=$INDEXER_HOME/venv/bin/python -m hermes.indexer webhook
Restart=on-failure
RestartSec=10
Environment=INDEXER_CONFIG=$INDEXER_CONFIG

[Install]
WantedBy=multi-user.target
SERVICE

echo "[indexer] Creating systemd timer for reconcile..."
sudo tee /etc/systemd/system/hermes-indexer-reconcile.service > /dev/null << SERVICE
[Unit]
Description=Hermes Codebase Indexer Reconcile

[Service]
Type=oneshot
User=ubuntu
ExecStart=$INDEXER_HOME/venv/bin/python -m hermes.indexer reconcile --once
Environment=INDEXER_CONFIG=$INDEXER_CONFIG
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
echo "  Config:       ${INDEXER_CONFIG}"
echo "  Mirrors:      ${MIRRORS_ROOT}"
echo "  Webhook:      systemctl start hermes-indexer-webhook"
echo "  Reconcile:    systemctl start hermes-indexer-reconcile.timer"
echo ""
echo "  Add an allowlist entry, then run:"
echo "    python -m hermes.indexer first-index owner/repo"
