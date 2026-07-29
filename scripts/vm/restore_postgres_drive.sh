#!/usr/bin/env bash
# Wayfinder #50/#54 (#48 MEM-6) — Restore Postgres dumps + secrets from Drive.
#
# Downloads dumps and secrets.age from Drive, decrypts secrets with the age
# unlock key, and pg_restore's into target databases.
#
# Usage:
#   ./restore_postgres_drive.sh <age-identity-file> [--dry-run]
#
#   age-identity-file : path to the age private key for decrypting secrets
#   --dry-run         : download and decrypt but do NOT run pg_restore
#
# Prerequisites:
#   - age, pg_restore installed
#   - rclone configured with "gdrive:" remote
#   - The age identity (unlock key) file — NEVER on Drive; operator supplies it.
#
# Environment variables:
#   Same as backup_postgres_drive.sh for DB connection targets:
#   HERMES_PGHOST, HERMES_PGPORT, HERMES_PGDB_HERMES, HERMES_ROLE
#   HERMES_PGDB_CODEBASE_INDEX, HERMES_INDEX_ROLE
#   HONCHO_PGHOST, HONCHO_PGPORT, HONCHO_ROLE, HONCHO_PGDB

set -euo pipefail

# ---------------------------------------------------------------------------
# Configurable defaults
# ---------------------------------------------------------------------------
HERMES_PGHOST="${HERMES_PGHOST:-127.0.0.1}"
HERMES_PGPORT="${HERMES_PGPORT:-5433}"
HERMES_PGDB_HERMES="${HERMES_PGDB_HERMES:-hermes}"
HERMES_ROLE="${HERMES_ROLE:-hermes_app}"
HERMES_PGDB_CODEBASE_INDEX="${HERMES_PGDB_CODEBASE_INDEX:-codebase_index}"
HERMES_INDEX_ROLE="${HERMES_INDEX_ROLE:-codebase_index_app}"
HONCHO_PGHOST="${HONCHO_PGHOST:-127.0.0.1}"
HONCHO_PGPORT="${HONCHO_PGPORT:-5432}"
HONCHO_ROLE="${HONCHO_ROLE:-postgres}"
HONCHO_PGDB="${HONCHO_PGDB:-postgres}"

GDRIVE_REMOTE="${GDRIVE_REMOTE:-gdrive:}"
DRIVE_FOLDER_ID="${DRIVE_FOLDER_ID:-17yovLP4BK1L_2jJKXbu4H4F-1kiGXzQM}"

# Which backup to restore — default: latest daily
RESTORE_SOURCE="${RESTORE_SOURCE:-daily}"   # "daily" or "weekly"
RESTORE_DATE="${RESTORE_DATE:-}"            # explicit YYYY-MM-DD; empty = latest

DRY_RUN=false
IDENTITY_FILE=""

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
usage() {
    printf 'Usage: %s <age-identity-file> [--dry-run]\n' "$0"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --) shift; break ;;
        -*|'') usage ;;
        *)  IDENTITY_FILE="$1"; shift ;;
    esac
done

if [[ -z "$IDENTITY_FILE" ]]; then
    usage
fi

if [[ ! -f "$IDENTITY_FILE" ]]; then
    printf '[restore][FATAL] age identity file not found: %s\n' "$IDENTITY_FILE" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { printf '[restore] %s\n' "$*"; }
fail() { printf '[restore][FATAL] %s\n' "$*" >&2; exit 1; }

cleanup() {
    if [[ -n "${TEMP_DIR:-}" && -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
        log "cleaned temp directory"
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

command -v age >/dev/null 2>&1 || fail "age not found — install age"
command -v pg_restore >/dev/null 2>&1 || fail "pg_restore not found — install postgresql-client-16"
command -v rclone >/dev/null 2>&1 || fail "rclone not found — install rclone"

# ---------------------------------------------------------------------------
# Step 1: Determine the source date (latest from Drive)
# ---------------------------------------------------------------------------

TEMP_DIR="$(mktemp -d)"
log "working directory: ${TEMP_DIR}"

if [[ -z "$RESTORE_DATE" ]]; then
    log "finding latest ${RESTORE_SOURCE} backup on Drive..."
    RESTORE_DATE="$(rclone lsd "${GDRIVE_REMOTE}hermes-pg/${RESTORE_SOURCE}/" \
        --drive-root-folder-id "${DRIVE_FOLDER_ID}" 2>/dev/null | \
        awk '{print $NF}' | sort | tail -n1)" || true
    if [[ -z "$RESTORE_DATE" ]]; then
        fail "no ${RESTORE_SOURCE} backups found on Drive"
    fi
    log "latest backup date: ${RESTORE_DATE}"
fi

# ---------------------------------------------------------------------------
# Step 2: Download dumps
# ---------------------------------------------------------------------------

log "downloading dumps from hermes-pg/${RESTORE_SOURCE}/${RESTORE_DATE}/ ..."
rclone copy "${GDRIVE_REMOTE}hermes-pg/${RESTORE_SOURCE}/${RESTORE_DATE}/" \
    "$TEMP_DIR" \
    --drive-root-folder-id "${DRIVE_FOLDER_ID}" 2>&1 || fail "rclone download failed"

for f in hermes.dump codebase_index.dump honcho.dump; do
    if [[ ! -s "${TEMP_DIR}/${f}" ]]; then
        fail "downloaded dump missing or empty: ${TEMP_DIR}/${f}"
    fi
    log "  ${f} OK ($(stat -f%z "${TEMP_DIR}/${f}" 2>/dev/null || stat -c%s "${TEMP_DIR}/${f}" 2>/dev/null) bytes)"
done

# ---------------------------------------------------------------------------
# Step 3: Download and decrypt secrets
# ---------------------------------------------------------------------------

log "downloading secrets.age from Drive..."
rclone copyto "${GDRIVE_REMOTE}hermes-pg/secrets/secrets.age" \
    "${TEMP_DIR}/secrets.age" \
    --drive-root-folder-id "${DRIVE_FOLDER_ID}" 2>&1 || fail "rclone secrets download failed"

log "decrypting secrets with age identity..."
age -d -i "$IDENTITY_FILE" -o "${TEMP_DIR}/secrets.tar" "${TEMP_DIR}/secrets.age" || \
    fail "age decryption failed — check identity file"
tar -xf "${TEMP_DIR}/secrets.tar" -C "$TEMP_DIR" || fail "tar extraction failed"

# Display what was in the archive
if [[ -f "${TEMP_DIR}/secrets/.env" ]]; then
    log "  decrypted: secrets/.env"
fi
if [[ -f "${TEMP_DIR}/secrets/rclone.conf" ]]; then
    log "  decrypted: secrets/rclone.conf"
fi

# ---------------------------------------------------------------------------
# Step 4: pg_restore into target databases
# ---------------------------------------------------------------------------

if [[ "$DRY_RUN" == true ]]; then
    log "DRY RUN — skipping pg_restore. Would restore into:"
    log "  Hermes DB:       ${HERMES_PGDB_HERMES} on ${HERMES_PGHOST}:${HERMES_PGPORT}"
    log "  Codebase index:  ${HERMES_PGDB_CODEBASE_INDEX} on ${HERMES_PGHOST}:${HERMES_PGPORT}"
    log "  Honcho DB:       ${HONCHO_PGDB} on ${HONCHO_PGHOST}:${HONCHO_PGPORT}"
    echo ""
    echo "================================================"
    echo " DRY RUN complete — no databases modified"
    echo "================================================"
    exit 0
fi

log "restoring Hermes DB..."
PGPASSWORD="${HERMES_PGPASSWORD:-}" \
pg_restore -h "$HERMES_PGHOST" -p "$HERMES_PGPORT" \
    -U "$HERMES_ROLE" -d "$HERMES_PGDB_HERMES" --clean --if-exists \
    "${TEMP_DIR}/hermes.dump" 2>&1 || fail "pg_restore failed for ${HERMES_PGDB_HERMES}"
log "  hermes.dump restored"

log "restoring codebase index DB..."
PGPASSWORD="${HERMES_INDEX_PGPASSWORD:-}" \
pg_restore -h "$HERMES_PGHOST" -p "$HERMES_PGPORT" \
    -U "$HERMES_INDEX_ROLE" -d "$HERMES_PGDB_CODEBASE_INDEX" --clean --if-exists \
    "${TEMP_DIR}/codebase_index.dump" 2>&1 || fail "pg_restore failed for ${HERMES_PGDB_CODEBASE_INDEX}"
log "  codebase_index.dump restored"

log "restoring Honcho Postgres..."
PGPASSWORD="${HONCHO_PGPASSWORD:-}" \
pg_restore -h "$HONCHO_PGHOST" -p "$HONCHO_PGPORT" \
    -U "$HONCHO_ROLE" -d "$HONCHO_PGDB" --clean --if-exists \
    "${TEMP_DIR}/honcho.dump" 2>&1 || fail "pg_restore failed for Honcho DB"
log "  honcho.dump restored"

echo ""
echo "================================================"
echo " Restore complete"
echo "================================================"
echo " Restored from:  ${RESTORE_SOURCE}/${RESTORE_DATE}"
echo " Hermes DB:      ${HERMES_PGDB_HERMES}"
echo " Codebase index: ${HERMES_PGDB_CODEBASE_INDEX}"
echo " Honcho DB:      ${HONCHO_PGDB}"
echo " Decrypted:      ${TEMP_DIR}/secrets/"
echo ""
echo " Next steps:"
echo "   1. Source the decrypted .env: source ${TEMP_DIR}/secrets/.env"
echo "   2. Restart Hermes services"
echo "   3. Re-fetch repo working trees from allowlist"
echo "================================================"
