#!/usr/bin/env bash
# Honcho self-hosted deploy — D-A/D-E adopted 2026-08-04 (map #76 Tasks 3–4).
#
# Idempotent: safe to re-run at any point. Brings up Honcho v3.0.12 on the
# shared Postgres 16 (:5433) as the third logical DB `honcho`, with systemd
# units for the API (:8000) and Deriver, then provisions the five persona
# workspaces/peers (setup/honcho-workspaces.py).
#
# Prerequisites: Ubuntu 24.04, Postgres 16 on 127.0.0.1:5433 (installed by
# setup/install.sh), passwordless sudo, uv on PATH.
#
# Env overrides: HONCHO_HOME (default /opt/honcho), HONCHO_DB_PASSWORD
# (generated if unset), HONCHO_BASE_URL (default http://127.0.0.1:8000).

set -euo pipefail

HONCHO_HOME="${HONCHO_HOME:-/opt/honcho}"
HONCHO_DB_PASSWORD="${HONCHO_DB_PASSWORD:-}"
HONCHO_BASE_URL="${HONCHO_BASE_URL:-http://127.0.0.1:8000}"
HONCHO_TAG="${HONCHO_TAG:-v3.0.12}"
ENV_FILE="$HONCHO_HOME/.env"

log() { printf '[honcho] %s\n' "$*"; }
fail() { printf '[honcho][FATAL] %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 0. Preflight
# ---------------------------------------------------------------------------
command -v uv >/dev/null 2>&1 || fail "uv not found — install it (https://docs.astral.sh/uv/)"
pg_isready -h 127.0.0.1 -p 5433 -q 2>/dev/null || \
    fail "Postgres 16 not ready on 127.0.0.1:5433 — run setup/install.sh first"

# ---------------------------------------------------------------------------
# 1. Source checkout + venv (idempotent)
# ---------------------------------------------------------------------------
if [ ! -d "$HONCHO_HOME/.git" ]; then
    log "cloning honcho ${HONCHO_TAG} into ${HONCHO_HOME}..."
    sudo mkdir -p "$HONCHO_HOME"
    sudo chown "$USER":"$USER" "$HONCHO_HOME"
    git clone --depth 1 --branch "$HONCHO_TAG" \
        https://github.com/plastic-labs/honcho.git "$HONCHO_HOME"
fi
if [ ! -d "$HONCHO_HOME/.venv" ]; then
    log "uv sync (first build on ARM64 takes a few minutes)..."
    (cd "$HONCHO_HOME" && uv sync)
fi

# ---------------------------------------------------------------------------
# 2. DB role + database + pgvector (idempotent)
# ---------------------------------------------------------------------------
if [ -z "$HONCHO_DB_PASSWORD" ] && [ -f "$ENV_FILE" ]; then
    HONCHO_DB_PASSWORD="$(
        sed -n 's|^DB_CONNECTION_URI=.*honcho_app:\([^@]*\)@.*|\1|p' "$ENV_FILE" \
            | head -n1
    )"
fi
if [ -z "$HONCHO_DB_PASSWORD" ]; then
    HONCHO_DB_PASSWORD="$(openssl rand -hex 16)"
fi

PSQL_SUPER="sudo -n -u postgres psql -h /var/run/postgresql -p 5433 -v ON_ERROR_STOP=1"
if ! $PSQL_SUPER -tAc "SELECT 1 FROM pg_roles WHERE rolname='honcho_app'" | grep -q 1; then
    log "creating role honcho_app..."
    $PSQL_SUPER -c "CREATE ROLE honcho_app LOGIN PASSWORD '$HONCHO_DB_PASSWORD'"
fi
if ! $PSQL_SUPER -tAc "SELECT 1 FROM pg_database WHERE datname='honcho'" | grep -q 1; then
    log "creating database honcho (owner honcho_app)..."
    $PSQL_SUPER -c "CREATE DATABASE honcho OWNER honcho_app"
fi
if ! $PSQL_SUPER -d honcho -tAc "SELECT 1 FROM pg_extension WHERE extname='vector'" | grep -q 1; then
    log "creating extension vector in honcho..."
    $PSQL_SUPER -d honcho -c "CREATE EXTENSION vector"
fi

# ---------------------------------------------------------------------------
# 3. Env file (first run only; never overwrite)
# ---------------------------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
    log "writing ${ENV_FILE} from template..."
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    sed \
        -e "s|__HONCHO_DB_PASSWORD__|$HONCHO_DB_PASSWORD|" \
        -e "s|__MINIMAX_API_KEY__|$(grep -E '^MINIMAX_API_KEY=' /home/ubuntu/hermes/.env 2>/dev/null | head -n1 | cut -d= -f2- || true)|" \
        "$SCRIPT_DIR/honcho/honcho.env.example" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
fi

# ---------------------------------------------------------------------------
# 4. Systemd units (idempotent)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sudo install -m 644 "$SCRIPT_DIR/honcho/honcho-api.service" \
    "$SCRIPT_DIR/honcho/honcho-deriver.service" /etc/systemd/system/
sudo systemctl daemon-reload
if ! systemctl is-active --quiet honcho-api; then
    log "enabling honcho-api + honcho-deriver..."
    sudo systemctl enable --now honcho-api.service honcho-deriver.service
    sleep 4
fi

# ---------------------------------------------------------------------------
# 5. Alembic migrations (idempotent)
# ---------------------------------------------------------------------------
if ! $PSQL_SUPER -d honcho -tAc "SELECT 1 FROM alembic_version" 2>/dev/null | grep -q 1; then
    log "applying alembic migrations..."
    (cd "$HONCHO_HOME" && uv run alembic upgrade head)
fi

# ---------------------------------------------------------------------------
# 6. Workspace/peer provisioning
# ---------------------------------------------------------------------------
log "provisioning persona workspaces/peers via ${HONCHO_BASE_URL}..."
python3 "$SCRIPT_DIR/honcho-workspaces.py" --base-url "$HONCHO_BASE_URL"

log "done — honcho-api and honcho-deriver active; smoke gate j now satisfiable"
