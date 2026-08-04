#!/usr/bin/env bash
# Hermes reboot install bootstrap (ADR 0005 / ticket #81).
#
# Thin chainer that runs the deterministic install phases in order. The
# unscripted tail (Tailscale auth, hermes-agent gateway, profile apply,
# cron registration) lives in INSTALL.md; this script only handles the
# phase that can be scripted deterministically.
#
# Phases:
#   0. Preflight — OS is Ubuntu 24.04 aarch64, scripts/vm/*.sh exist.
#   1. .env validation — every REQUIRED key is non-empty.
#   2. Provision Hermes Postgres (scripts/vm/provision-hermes-postgres.sh).
#   3. Apply DB migrations (db/migrate.sh) as the DB-owner roles; the
#      pgvector extension needs a one-time superuser CREATE EXTENSION first
#      (prototype #77 finding: migrations were never applied by the chain).
#   4. Provision codebase indexer (scripts/vm/provision-indexer.sh) — before
#      the smoke gate, which checks codebase_index tables (#77 finding).
#   5. Smoke Postgres (scripts/vm/smoke-hermes-postgres.sh) — halts on FAIL.
#   6. Optional Drive restore — only if RESTORE_KEY_PATH is set in .env
#      (DR tier, unverified per ADR 0005 D3).
#   7. Summary — point operator at INSTALL.md Step 2.
#
# Redo semantics: re-run from the top. Each chained script is idempotent
# by design (see ADR 0005 D2 / research docs/research/2026-08-04-fresh-install-inventory.md §d).
# The script halts on the first failing smoke (`set -euo pipefail`).
#
# Usage:
#   bash setup/install.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

phase() { printf '\n=== [install.sh] phase %s — %s ===\n' "$1" "$2"; }
log()   { printf '[install.sh] %s\n' "$*"; }
fail()  { printf '[install.sh][FATAL] %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Phase 0: preflight
# ---------------------------------------------------------------------------
phase 0 "preflight"

# OS baseline — Ubuntu 24.04 aarch64 (ADR 0006).
if [[ ! -f /etc/os-release ]]; then
    fail "/etc/os-release not found — this script targets Ubuntu 24.04 aarch64"
fi
# shellcheck disable=SC1091
. /etc/os-release
if [[ "${VERSION_ID:-}" != "24.04" ]]; then
    fail "OS VERSION_ID is '${VERSION_ID:-?}', expected '24.04' (Ubuntu 24.04 LTS)"
fi
if [[ "${ID:-}" != "ubuntu" ]]; then
    fail "OS ID is '${ID:-?}', expected 'ubuntu'"
fi
if [[ "$(uname -m)" != "aarch64" ]]; then
    fail "uname -m is '$(uname -m)', expected 'aarch64'"
fi
log "OS baseline OK: ${ID} ${VERSION_ID} $(uname -m)"

# Required scripts must exist relative to the repo root.
for f in \
    scripts/vm/provision-hermes-postgres.sh \
    scripts/vm/smoke-hermes-postgres.sh \
    scripts/vm/provision-indexer.sh \
    scripts/vm/restore_postgres_drive.sh \
    scripts/vm/smoke-restore.sh; do
    if [[ ! -f "${f}" ]]; then
        fail "missing required script: ${f}"
    fi
done
if [[ ! -f db/migrate.sh ]]; then
    fail "db/migrate.sh not found — run this script from the repo root"
fi
log "required scripts/vm/*.sh present"

# ---------------------------------------------------------------------------
# Phase 1: .env presence + required-key validation
# ---------------------------------------------------------------------------
phase 1 ".env validation"

if [[ ! -f .env ]]; then
    fail ".env not found at repo root — copy .env.example to .env and fill REQUIRED keys (see INSTALL.md Step 1)"
fi

REQUIRED_KEYS=(
    DISCORD_BOT_TOKEN_ASSISTANT
    DISCORD_BOT_TOKEN_TUTOR
    DISCORD_BOT_TOKEN_MAIN_AGENT
    MINIMAX_API_KEY
    DISCORD_HOME_CHANNEL
    HERMES_HOME
)

missing=()
for key in "${REQUIRED_KEYS[@]}"; do
    val="$(grep -E "^${key}=" .env | head -n1 | cut -d= -f2- || true)"
    if [[ -z "${val}" ]]; then
        missing+=("${key}")
    fi
done

if (( ${#missing[@]} > 0 )); then
    fail "missing REQUIRED keys in .env: ${missing[*]} — see INSTALL.md Step 1 and .env.example"
fi
log ".env validates: ${#REQUIRED_KEYS[@]} required keys present"

# Export HERMES_HOME so downstream scripts pick the operator-chosen path
# (their /home/ubuntu defaults are historical; see INSTALL.md "Path notes").
# shellcheck disable=SC1091
set -a
. .env
set +a

# ---------------------------------------------------------------------------
# Phase 2: provision Hermes Postgres
# ---------------------------------------------------------------------------
phase 2 "provision Hermes Postgres"
bash scripts/vm/provision-hermes-postgres.sh

# ---------------------------------------------------------------------------
# Phase 3: apply DB migrations.
#
# migrate.sh defaults HERMES_PGUSER to $USER, which lacks DDL rights on the
# owner-role databases; run each migration as its DB-owner role. CREATE
# EXTENSION vector additionally requires superuser, so it is done once as
# postgres over the peer-auth unix socket (passwordless sudo is already a
# hard requirement of the chained scripts).
# ---------------------------------------------------------------------------
phase 3 "apply DB migrations"
HERMES_PGUSER="${HERMES_ROLE:-hermes_app}" bash db/migrate.sh hermes
sudo -n -u postgres psql -h /var/run/postgresql -p "${HERMES_PGPORT:-5433}" \
    -d "${HERMES_PGDB_CODEBASE_INDEX:-codebase_index}" \
    -c 'CREATE EXTENSION IF NOT EXISTS vector;' >/dev/null
HERMES_PGUSER="${HERMES_INDEX_ROLE:-codebase_index_app}" bash db/migrate.sh codebase_index

# ---------------------------------------------------------------------------
# Phase 4: provision codebase indexer (schema already applied in phase 3;
# its own migrate call then no-ops via schema_migrations).
# ---------------------------------------------------------------------------
phase 4 "provision codebase indexer"
bash scripts/vm/provision-indexer.sh

# ---------------------------------------------------------------------------
# Phase 5: smoke Postgres — hard gate (halts on FAIL via set -e).
# NOTE (#77): check j requires Honcho on :5432, which is outside the scripted
# core (INSTALL.md Step 2 tail); until Honcho is up, expect FAIL:j here and
# re-run the gate after the tail.
# ---------------------------------------------------------------------------
phase 5 "smoke Hermes Postgres"
if ! bash scripts/vm/smoke-hermes-postgres.sh; then
    fail "smoke-hermes-postgres.sh failed — fix Postgres before re-running"
fi

# ---------------------------------------------------------------------------
# Phase 6: optional Drive restore (DR tier; unverified per ADR 0005 D3).
# Skipped when RESTORE_KEY_PATH is unset.
# ---------------------------------------------------------------------------
phase 6 "optional Drive restore"
if [[ -n "${RESTORE_KEY_PATH:-}" ]]; then
    log "RESTORE_KEY_PATH set — running restore + smoke (DR tier, unverified)"
    if [[ ! -f "${RESTORE_KEY_PATH}" ]]; then
        fail "RESTORE_KEY_PATH='${RESTORE_KEY_PATH}' does not exist"
    fi
    bash scripts/vm/restore_postgres_drive.sh "${RESTORE_KEY_PATH}"
    bash scripts/vm/smoke-restore.sh "${RESTORE_KEY_PATH}"
else
    log "RESTORE_KEY_PATH unset — skipping restore (zero-data fresh install)"
fi

# ---------------------------------------------------------------------------
# Phase 7: summary
# ---------------------------------------------------------------------------
phase 7 "summary"
cat <<'EOF'

Scripted phases complete:
  - Hermes Postgres provisioned on 127.0.0.1:5433 (pgvector)
  - Postgres smoke gate passed
  - Codebase indexer provisioned

Next: open INSTALL.md and follow Step 2 (unscripted tail):
  - hermes-agent gateway + hermes-gateway.service (ADR 0004 — out of repo)
  - 5-profile provisioning via hermes/profiles/provision.py plan
  - cron registration
  - Ollama is NOT installed (embedding provider TBD — do not install)

Then Step 3 (acceptance checklist) to mark "working Hermes".

EOF