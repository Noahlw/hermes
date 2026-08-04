#!/usr/bin/env bash
# Wayfinder #51 (#48 MEM-6) — Daily three-DB pg_dump to Google Drive.
#
# Dumps Hermes DB, codebase index DB, and Honcho Postgres in Postgres custom
# format, then uploads to Drive under hermes-pg/.
#
# Usage:
#   ./backup_postgres_drive.sh            # daily dump only
#   ./backup_postgres_drive.sh --weekly   # daily + weekly dump
#
# Prerequisites:
#   - pg_dump (Postgres 16) on PATH
#   - rclone configured with "gdrive:" remote
#   - Network access to Drive (rclone remote)
#
# Environment variables (all have sensible defaults for the VM):
#   HERMES_PGHOST, HERMES_PGPORT, HERMES_PGDB_HERMES, HERMES_ROLE
#   HERMES_PGDB_CODEBASE_INDEX, HERMES_INDEX_ROLE
#   HONCHO_PGHOST, HONCHO_PGPORT, HONCHO_ROLE, HONCHO_PGDB

set -euo pipefail

# ---------------------------------------------------------------------------
# Configurable defaults
# ---------------------------------------------------------------------------
# Hermes Postgres (systemd, :5433)
HERMES_PGHOST="${HERMES_PGHOST:-127.0.0.1}"
HERMES_PGPORT="${HERMES_PGPORT:-5433}"
HERMES_PGDB_HERMES="${HERMES_PGDB_HERMES:-hermes}"
HERMES_ROLE="${HERMES_ROLE:-hermes_app}"
HERMES_PGDB_CODEBASE_INDEX="${HERMES_PGDB_CODEBASE_INDEX:-codebase_index}"
HERMES_INDEX_ROLE="${HERMES_INDEX_ROLE:-codebase_index_app}"

# Honcho Postgres (Docker, :5432)
# Honcho (shared Postgres 16 on :5433 — reboot D-A, 2026-08-04; Docker-era
# defaults removed)
HONCHO_PGHOST="${HONCHO_PGHOST:-127.0.0.1}"
HONCHO_PGPORT="${HONCHO_PGPORT:-5433}"
HONCHO_ROLE="${HONCHO_ROLE:-honcho_app}"
HONCHO_PGDB="${HONCHO_PGDB:-honcho}"

# Drive
GDRIVE_REMOTE="${GDRIVE_REMOTE:-gdrive:}"
DRIVE_FOLDER_ID="${DRIVE_FOLDER_ID:-17yovLP4BK1L_2jJKXbu4H4F-1kiGXzQM}"

# Retention (for prune)
DAILY_RETENTION="${DAILY_RETENTION:-14}"
WEEKLY_RETENTION="${WEEKLY_RETENTION:-4}"

# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------
DO_WEEKLY=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --weekly) DO_WEEKLY=true; shift ;;
        --) shift; break ;;
        *)  printf 'Usage: %s [--weekly]\n' "$0"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { printf '[backup] %s\n' "$*"; }
fail() { printf '[backup][FATAL] %s\n' "$*" >&2; exit 1; }

cleanup() {
    if [[ -n "${TEMP_DIR:-}" && -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
        log "cleaned temp directory"
    fi
}

# ---------------------------------------------------------------------------
# Prune: remove old dated directories under a Drive prefix, keeping the N most
# recent. Only operates within hermes-pg/ — never touches cognee or other dirs.
# ---------------------------------------------------------------------------
prune_drive_dir() {
    local prefix="$1"      # e.g. hermes-pg/daily or hermes-pg/weekly
    local keep="$2"        # number of directories to retain

    log "pruning ${prefix}/ — keeping ${keep} most recent"

    # List directories sorted by name (ascending = oldest first for YYYY-MM-DD)
    local dirs
    dirs="$(rclone lsd "${GDRIVE_REMOTE}${prefix}/" \
        --drive-root-folder-id "${DRIVE_FOLDER_ID}" 2>/dev/null | awk '{print $NF}' | sort)" || true

    if [[ -z "$dirs" ]]; then
        log "  no directories found under ${prefix}/ — nothing to prune"
        return 0
    fi

    local total
    total="$(echo "$dirs" | wc -l | tr -d ' ')"
    if (( total <= keep )); then
        log "  ${total} dir(s) ≤ ${keep} — no pruning needed"
        return 0
    fi

    # Lines to delete = all but the last $keep
    local to_delete
    to_delete="$(echo "$dirs" | head -n -${keep})"

    local count=0
    while IFS= read -r dir; do
        if [[ -n "$dir" ]]; then
            log "  removing old: ${prefix}/${dir}/"
            rclone purge "${GDRIVE_REMOTE}${prefix}/${dir}/" \
                --drive-root-folder-id "${DRIVE_FOLDER_ID}" 2>&1 || \
                log "  WARN: failed to purge ${prefix}/${dir}/ (may have been purged already)"
            ((count++))
        fi
    done <<< "$to_delete"

    log "  pruned ${count} old director(ies) from ${prefix}/"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

command -v pg_dump >/dev/null 2>&1 || fail "pg_dump not found — install postgresql-client-16"
command -v rclone >/dev/null 2>&1 || fail "rclone not found — install rclone"

# ---------------------------------------------------------------------------
# Dump phase
# ---------------------------------------------------------------------------

TEMP_DIR="$(mktemp -d)"
DATE_STR="$(date -u +%Y-%m-%d)"
log "dump directory: ${TEMP_DIR}"
log "date: ${DATE_STR}"

log "dumping Hermes DB (${HERMES_PGDB_HERMES})..."
PGPASSWORD="${HERMES_PGPASSWORD:-}" \
pg_dump -h "$HERMES_PGHOST" -p "$HERMES_PGPORT" \
    -U "$HERMES_ROLE" -Fc \
    -f "${TEMP_DIR}/hermes.dump" \
    "$HERMES_PGDB_HERMES" 2>&1 || fail "pg_dump failed for ${HERMES_PGDB_HERMES}"
log "  hermes.dump OK"

log "dumping codebase index DB (${HERMES_PGDB_CODEBASE_INDEX})..."
PGPASSWORD="${HERMES_INDEX_PGPASSWORD:-}" \
pg_dump -h "$HERMES_PGHOST" -p "$HERMES_PGPORT" \
    -U "$HERMES_INDEX_ROLE" -Fc \
    -f "${TEMP_DIR}/codebase_index.dump" \
    "$HERMES_PGDB_CODEBASE_INDEX" 2>&1 || fail "pg_dump failed for ${HERMES_PGDB_CODEBASE_INDEX}"
log "  codebase_index.dump OK"

log "dumping Honcho Postgres (${HONCHO_PGDB})..."
PGPASSWORD="${HONCHO_PGPASSWORD:-}" \
pg_dump -h "$HONCHO_PGHOST" -p "$HONCHO_PGPORT" \
    -U "$HONCHO_ROLE" -Fc \
    -f "${TEMP_DIR}/honcho.dump" \
    "$HONCHO_PGDB" 2>&1 || fail "pg_dump failed for Honcho DB"
log "  honcho.dump OK"

# Verify dumps exist and have content
for f in hermes.dump codebase_index.dump honcho.dump; do
    if [[ ! -s "${TEMP_DIR}/${f}" ]]; then
        fail "${f} is empty or missing"
    fi
done

# ---------------------------------------------------------------------------
# Upload phase
# ---------------------------------------------------------------------------

log "uploading daily dump to ${GDRIVE_REMOTE}hermes-pg/daily/${DATE_STR}/ ..."
rclone copy "$TEMP_DIR" \
    "${GDRIVE_REMOTE}hermes-pg/daily/${DATE_STR}/" \
    --drive-root-folder-id "${DRIVE_FOLDER_ID}" 2>&1 || fail "rclone daily upload failed"
log "daily upload complete"

if [[ "$DO_WEEKLY" == true ]]; then
    log "uploading weekly dump to ${GDRIVE_REMOTE}hermes-pg/weekly/${DATE_STR}/ ..."
    rclone copy "$TEMP_DIR" \
        "${GDRIVE_REMOTE}hermes-pg/weekly/${DATE_STR}/" \
        --drive-root-folder-id "${DRIVE_FOLDER_ID}" 2>&1 || fail "rclone weekly upload failed"
    log "weekly upload complete"
fi

# ---------------------------------------------------------------------------
# Prune phase (runs after every backup, regardless of daily/weekly mode)
# ---------------------------------------------------------------------------
prune_drive_dir "hermes-pg/daily" "${DAILY_RETENTION}"
prune_drive_dir "hermes-pg/weekly" "${WEEKLY_RETENTION}"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
log "backup complete — all dumps uploaded to Drive"
