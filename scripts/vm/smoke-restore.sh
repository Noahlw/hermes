#!/usr/bin/env bash
# Wayfinder #54 — Same-VM restore smoke test.
#
# Downloads dumps + secrets.age from Drive, decrypts, and pg_restore's into
# DISPOSABLE databases (hermes_smoke, codebase_index_smoke, honcho_smoke).
# Does NOT touch live production DBs (hermes, codebase_index, honcho/postgres).
#
# Smoke checks:
#   - age decryption works (decrypts secrets.age)
#   - pg_restore of each dump into a disposable DB succeeds
#   - SELECT from a restored table returns expected data
#
# Usage:
#   ./smoke-restore.sh <age-identity-file>
#
# Exit codes:
#   0 = all smoke checks pass
#   1 = any check fails
#
# NOTE: Hermes Postgres (:5433) uses sudo -u postgres via Unix socket because
# pg_hba only trusts app roles for exact DB names. Honcho (:5432) uses TCP.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configurable defaults
# ---------------------------------------------------------------------------
HERMES_PGPORT="${HERMES_PGPORT:-5433}"
HERMES_ROLE="${HERMES_ROLE:-hermes_app}"
HERMES_INDEX_ROLE="${HERMES_INDEX_ROLE:-codebase_index_app}"
HONCHO_PGHOST="${HONCHO_PGHOST:-127.0.0.1}"
HONCHO_PGPORT="${HONCHO_PGPORT:-5432}"
HONCHO_ROLE="${HONCHO_ROLE:-postgres}"

GDRIVE_REMOTE="${GDRIVE_REMOTE:-gdrive:}"
DRIVE_FOLDER_ID="${DRIVE_FOLDER_ID:-17yovLP4BK1L_2jJKXbu4H4F-1kiGXzQM}"

SMOKE_DB_HERMES="hermes_smoke"
SMOKE_DB_INDEX="codebase_index_smoke"
SMOKE_DB_HONCHO="honcho_smoke"

IDENTITY_FILE="${1:-}"
FAILED_CHECKS=()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { printf '[smoke] %s\n' "$*"; }
fail() { printf '[smoke][FATAL] %s\n' "$*" >&2; exit 1; }

check() {
    local label="$1"
    shift
    local out
    if out="$("$@" 2>&1)"; then
        log "  [PASS] ${label}"
    else
        log "  [FAIL] ${label}"
        log "    ${out}"
        FAILED_CHECKS+=("$label")
    fi
}

cleanup() {
    if [[ -n "${TEMP_DIR:-}" && -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
        log "cleaned temp directory"
    fi
}
trap cleanup EXIT

# Postgres access helpers:
SQL_HERMES() {
    sudo -n -u postgres psql -h /var/run/postgresql \
        -p "${HERMES_PGPORT}" -tA -X -v ON_ERROR_STOP=1 "$@"
}
SQL_HONCHO() {
    PGPASSWORD="${HONCHO_PGPASSWORD:-}" psql -h "$HONCHO_PGHOST" -p "$HONCHO_PGPORT" \
        -U postgres -tA -X -v ON_ERROR_STOP=1 "$@"
}

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

if [[ -z "$IDENTITY_FILE" ]]; then
    printf 'Usage: %s <age-identity-file>\n' "$0" >&2
    exit 1
fi
if [[ ! -f "$IDENTITY_FILE" ]]; then
    fail "age identity file not found: ${IDENTITY_FILE}"
fi

command -v age >/dev/null 2>&1        || fail "age not found"
command -v pg_dump >/dev/null 2>&1    || fail "pg_dump not found"
command -v pg_restore >/dev/null 2>&1 || fail "pg_restore not found"
command -v psql >/dev/null 2>&1       || fail "psql not found"
command -v rclone >/dev/null 2>&1     || fail "rclone not found"

# ---------------------------------------------------------------------------
# Safety: verify smoke DBs do not exist yet
# ---------------------------------------------------------------------------

for smoke_db in "$SMOKE_DB_HERMES" "$SMOKE_DB_INDEX"; do
    if SQL_HERMES -c "SELECT 1 FROM pg_database WHERE datname='${smoke_db}'" 2>/dev/null | grep -q 1; then
        fail "database ${smoke_db} already exists on :${HERMES_PGPORT}"
    fi
done
if SQL_HONCHO -c "SELECT 1 FROM pg_database WHERE datname='${SMOKE_DB_HONCHO}'" 2>/dev/null | grep -q 1; then
    fail "database ${SMOKE_DB_HONCHO} already exists on :${HONCHO_PGPORT}"
fi

# ---------------------------------------------------------------------------
# Step 1: Find latest daily backup
# ---------------------------------------------------------------------------

log "finding latest daily backup on Drive..."
RESTORE_DATE="$(rclone lsd "${GDRIVE_REMOTE}hermes-pg/daily/" \
    --drive-root-folder-id "${DRIVE_FOLDER_ID}" 2>/dev/null | \
    awk '{print $NF}' | sort | tail -n1)" || true

if [[ -z "$RESTORE_DATE" ]]; then
    fail "no daily backups found on Drive"
fi
log "using backup date: ${RESTORE_DATE}"

# ---------------------------------------------------------------------------
# Step 2: Download dumps + secrets
# ---------------------------------------------------------------------------

TEMP_DIR="$(mktemp -d)"
log "downloading dumps..."
# Make dumps readable by postgres user for pg_restore via sudo
chmod -R a+rX "$TEMP_DIR" 2>/dev/null || true
rclone copy "${GDRIVE_REMOTE}hermes-pg/daily/${RESTORE_DATE}/" \
    "$TEMP_DIR" --drive-root-folder-id "${DRIVE_FOLDER_ID}" || fail "rclone download failed"

log "downloading secrets.age..."
rclone copyto "${GDRIVE_REMOTE}hermes-pg/secrets/secrets.age" \
    "${TEMP_DIR}/secrets.age" --drive-root-folder-id "${DRIVE_FOLDER_ID}" || fail "rclone secrets failed"

# ---------------------------------------------------------------------------
# Step 3: Decrypt and verify dump contents
# ---------------------------------------------------------------------------

log "decrypting secrets.age..."
age -d -i "$IDENTITY_FILE" -o "${TEMP_DIR}/secrets.tar" "${TEMP_DIR}/secrets.age" || \
    fail "age decryption failed"
check "age decrypt + tar" tar -xf "${TEMP_DIR}/secrets.tar" -C "$TEMP_DIR"

for f in hermes.dump codebase_index.dump honcho.dump; do
    check "${f} downloaded (size > 0)" test -s "${TEMP_DIR}/${f}"
done

# ---------------------------------------------------------------------------
# Step 4: Create smoke databases and restore into them
# ---------------------------------------------------------------------------

check "create ${SMOKE_DB_HERMES}" SQL_HERMES \
    -c "CREATE DATABASE ${SMOKE_DB_HERMES} OWNER ${HERMES_ROLE};"
check "create ${SMOKE_DB_INDEX}" SQL_HERMES \
    -c "CREATE DATABASE ${SMOKE_DB_INDEX} OWNER ${HERMES_INDEX_ROLE};"
check "create ${SMOKE_DB_HONCHO}" SQL_HONCHO \
    -c "CREATE DATABASE ${SMOKE_DB_HONCHO} OWNER ${HONCHO_ROLE};"

check "restore ${SMOKE_DB_HERMES}" \
    sudo -n -u postgres pg_restore -h /var/run/postgresql -p "${HERMES_PGPORT}" \
        -d "${SMOKE_DB_HERMES}" "${TEMP_DIR}/hermes.dump"

check "restore ${SMOKE_DB_INDEX}" \
    sudo -n -u postgres pg_restore -h /var/run/postgresql -p "${HERMES_PGPORT}" \
        -d "${SMOKE_DB_INDEX}" "${TEMP_DIR}/codebase_index.dump"

check "restore ${SMOKE_DB_HONCHO}" \
    env PGPASSWORD="${HONCHO_PGPASSWORD:-}" pg_restore -h "$HONCHO_PGHOST" -p "$HONCHO_PGPORT" \
        -U "${HONCHO_ROLE}" -d "${SMOKE_DB_HONCHO}" "${TEMP_DIR}/honcho.dump"

# ---------------------------------------------------------------------------
# Step 5: Verify restored data with SELECT
# ---------------------------------------------------------------------------

log "verifying restored data..."

CHECK_HERMES_TABLE="$(sudo -n -u postgres psql -h /var/run/postgresql -p "${HERMES_PGPORT}" \
    -d "${SMOKE_DB_HERMES}" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null)"
if [[ "$CHECK_HERMES_TABLE" =~ ^[0-9]+$ ]] && (( CHECK_HERMES_TABLE > 0 )); then
    log "  [PASS] ${SMOKE_DB_HERMES}: ${CHECK_HERMES_TABLE} tables exist"
else
    log "  [FAIL] ${SMOKE_DB_HERMES}: no tables found (output: '${CHECK_HERMES_TABLE}')"
    FAILED_CHECKS+=("hermes_smoke_tables")
fi

CHECK_INDEX_ROWS="$(sudo -n -u postgres psql -h /var/run/postgresql -p "${HERMES_PGPORT}" \
    -d "${SMOKE_DB_INDEX}" -tAc \
    "SELECT count(*) FROM repos;" 2>/dev/null)"
if [[ "$CHECK_INDEX_ROWS" =~ ^[0-9]+$ ]]; then
    log "  [PASS] ${SMOKE_DB_INDEX}: ${CHECK_INDEX_ROWS} repos"
else
    log "  [FAIL] ${SMOKE_DB_INDEX}: could not query repos (output: '${CHECK_INDEX_ROWS}')"
    FAILED_CHECKS+=("codebase_index_smoke_repos")
fi

CHECK_HONCHO_ROWS="$(PGPASSWORD="${HONCHO_PGPASSWORD:-}" psql -h "$HONCHO_PGHOST" -p "$HONCHO_PGPORT" \
    -U postgres -d "${SMOKE_DB_HONCHO}" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null)"
if [[ "$CHECK_HONCHO_ROWS" =~ ^[0-9]+$ ]] && (( CHECK_HONCHO_ROWS > 0 )); then
    log "  [PASS] ${SMOKE_DB_HONCHO}: ${CHECK_HONCHO_ROWS} tables exist"
else
    log "  [FAIL] ${SMOKE_DB_HONCHO}: no tables found (output: '${CHECK_HONCHO_ROWS}')"
    FAILED_CHECKS+=("honcho_smoke_tables")
fi

# ---------------------------------------------------------------------------
# Step 6: Clean up smoke databases
# ---------------------------------------------------------------------------

log "cleaning up smoke databases..."
SQL_HERMES -c "DROP DATABASE IF EXISTS ${SMOKE_DB_HERMES};" 2>/dev/null || true
SQL_HERMES -c "DROP DATABASE IF EXISTS ${SMOKE_DB_INDEX};" 2>/dev/null || true
SQL_HONCHO -c "DROP DATABASE IF EXISTS ${SMOKE_DB_HONCHO};" 2>/dev/null || true
log "  smoke databases dropped"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
if (( ${#FAILED_CHECKS[@]} == 0 )); then
    log "ALL SMOKE CHECKS PASSED"
    exit 0
else
    log "SMOKE FAILED: ${#FAILED_CHECKS[@]} check(s) failed:"
    for c in "${FAILED_CHECKS[@]}"; do
        log "  - ${c}"
    done
    exit 1
fi
