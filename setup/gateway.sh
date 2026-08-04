#!/usr/bin/env bash
# Hermes in-repo gateway bring-up (D-B fork 2, ADR 0004 amendment, 2026-08-04).
#
# Idempotent. Provisions the hermes_agent runtime from this repo (ADR 0004
# amendment makes this repo the V1 runtime) into /opt/hermes-gateway:
#   1. Pre-flight — repo-root .env exists with REQUIRED keys; python3.12.
#   2. /opt/hermes-gateway + venv at /opt/hermes-gateway/venv.
#   3. pip install -e . into the venv.
#   4. plan_provision() → mkdir dirs, write any missing files (write-if-absent).
#   5. Install hermes-gateway.service into /etc/systemd/system.
#   6. systemctl enable --now hermes-gateway.
#   7. Wait up to 30 s for the unit to reach active (running).
#
# Redo = re-run from the top. No new idempotency machinery — the install
# phases above are already idempotent (venv exists check, pip install -e is
# a no-op when up to date, plan_provision file writes are write-if-absent,
# systemctl enable --now is idempotent).
#
# Usage:
#   sudo bash setup/gateway.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_HOME=/opt/hermes-gateway
VENV="$GATEWAY_HOME/venv"
SERVICE_SRC="$REPO_ROOT/setup/systemd/hermes-gateway.service"
SERVICE_DST=/etc/systemd/system/hermes-gateway.service

REQUIRED_KEYS=(
    DISCORD_BOT_TOKEN_ASSISTANT
    DISCORD_BOT_TOKEN_TUTOR
    DISCORD_BOT_TOKEN_MAIN_AGENT
    MINIMAX_API_KEY
    DISCORD_HOME_CHANNEL
    DISCORD_ALLOWED_USER_ID
    HERMES_HOME
)

log()  { printf '[gateway.sh] %s\n' "$*"; }
fail() { printf '[gateway.sh][FATAL] %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Pre-flight
# ---------------------------------------------------------------------------
log "preflight: repo root ${REPO_ROOT}"
[[ -f "$REPO_ROOT/.env" ]] || fail ".env not found at repo root — copy .env.example to .env and fill REQUIRED keys (see INSTALL.md Step 1)"

# Secrets live in the repo .env (systemd EnvironmentFile) — enforce 0600 so
# other local users cannot read tokens (ADR 0004 amendment install contract).
chmod 600 "$REPO_ROOT/.env"
log "preflight: .env permissions hardened to 0600"

missing=()
for key in "${REQUIRED_KEYS[@]}"; do
    val="$(grep -E "^${key}=" "$REPO_ROOT/.env" | head -n1 | cut -d= -f2- || true)"
    if [[ -z "${val}" ]]; then
        missing+=("$key")
    fi
done
if (( ${#missing[@]} > 0 )); then
    fail "missing REQUIRED keys in .env: ${missing[*]} — see INSTALL.md Step 1 and .env.example"
fi
log "preflight: ${#REQUIRED_KEYS[@]} required keys present"

if ! command -v python3.12 >/dev/null 2>&1; then
    fail "python3.12 not found on PATH — install python3.12 before running this script"
fi

# ---------------------------------------------------------------------------
# 2. Install root + venv
# ---------------------------------------------------------------------------
if [[ ! -d "$GATEWAY_HOME" ]]; then
    log "creating $GATEWAY_HOME"
    sudo mkdir -p "$GATEWAY_HOME"
    sudo chown ubuntu:ubuntu "$GATEWAY_HOME"
fi
if [[ ! -d "$VENV" ]]; then
    log "creating venv at $VENV"
    sudo -u ubuntu python3.12 -m venv "$VENV"
fi

# ---------------------------------------------------------------------------
# 3. pip install -e . (idempotent; pip is a no-op when up to date)
# ---------------------------------------------------------------------------
log "pip install -e ${REPO_ROOT} into $VENV"
sudo -u ubuntu "$VENV/bin/pip" install --quiet --upgrade pip
sudo -u ubuntu "$VENV/bin/pip" install --quiet -e "$REPO_ROOT"

# ---------------------------------------------------------------------------
# 4. plan_provision — write-if-absent profile artifacts under PROFILES_ROOT
#    (default ~/.hermes/profiles). plan_provision() returns ProvisionPlan;
#    apply = mkdir -p dirs, then write each (rel_path, content) only if absent.
# ---------------------------------------------------------------------------
PROFILES_ROOT="$(grep -E '^PROFILES_ROOT=' "$REPO_ROOT/.env" | head -n1 | cut -d= -f2- || true)"
export PROFILES_ROOT
log "applying plan_provision() under $PROFILES_ROOT"
sudo -u ubuntu "$VENV/bin/python" - <<'PY'
import os
from pathlib import Path
from hermes.profiles.config import DEFAULT_PROFILES_ROOT
from hermes.profiles.provision import plan_provision

root = Path(os.path.expanduser(os.environ.get("PROFILES_ROOT") or DEFAULT_PROFILES_ROOT))
plan = plan_provision(root=str(root))
errs = plan.validate()
if errs:
    raise SystemExit(f"plan_provision validation failed: {errs}")

for d in plan.dirs:
    (root / d).mkdir(parents=True, exist_ok=True)
for rel_path, content in plan.files:
    target = root / rel_path
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
print(f"[gateway.sh] plan_provision applied under {root}")
PY

# ---------------------------------------------------------------------------
# 5. Systemd unit
# ---------------------------------------------------------------------------
log "installing $SERVICE_DST"
sudo install -m 644 "$SERVICE_SRC" "$SERVICE_DST"
sudo systemctl daemon-reload

# ---------------------------------------------------------------------------
# 6. Enable + start (idempotent)
# ---------------------------------------------------------------------------
if ! systemctl is-enabled --quiet hermes-gateway; then
    log "enabling hermes-gateway"
    sudo systemctl enable hermes-gateway
fi
if ! systemctl is-active --quiet hermes-gateway; then
    log "starting hermes-gateway"
    sudo systemctl start hermes-gateway
fi

# ---------------------------------------------------------------------------
# 7. Health wait — poll up to 30 s for active state
# ---------------------------------------------------------------------------
log "waiting for hermes-gateway to reach active (max 30 s)..."
for _ in $(seq 1 30); do
    if systemctl is-active --quiet hermes-gateway; then
        log "hermes-gateway is active"
        # Active ≠ healthy: the unit can sit active while the bot fails to
        # log in or the runtime cannot start. --check validates config,
        # profiles, jobs and MCP tool registration; fail loudly otherwise.
        env_pairs="$(grep -E '^[A-Z_][A-Z0-9_]*=' "$REPO_ROOT/.env" | xargs -d '\n')"
        if sudo -u ubuntu env "$env_pairs" "$VENV/bin/python" -m hermes_agent --check \
                >/tmp/hermes-gateway-check.log 2>&1; then
            log "hermes_agent --check OK"
            exit 0
        fi
        sudo systemctl status hermes-gateway --no-pager || true
        fail "hermes_agent --check failed — see /tmp/hermes-gateway-check.log and 'journalctl -u hermes-gateway'"
    fi
    sleep 1
done

sudo systemctl status hermes-gateway --no-pager || true
fail "hermes-gateway did not become active within 30 s — check 'journalctl -u hermes-gateway'"