#!/usr/bin/env bash
# Wayfinder #50 — Encrypt secrets with an existing age key for Drive upload.
#
# Re-encrypts the same secrets archive that key-bootstrap.sh creates, then
# uploads to Drive. Useful when secrets change after initial bootstrap.
#
# Usage:
#   ./encrypt-secrets.sh <identity-file> [identity-file-path]
#
# Prerequisites:
#   - age, tar, rclone installed
#   - rclone configured with "gdrive:" remote
#
# Environment variables:
#   Same as key-bootstrap.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Configurable defaults
# ---------------------------------------------------------------------------
HERMES_HOME="${HERMES_HOME:-/home/ubuntu/.hermes}"
HERMES_ENV_PATH="${HERMES_ENV_PATH:-${HERMES_HOME}/.env}"
RCLONE_CONFIG="${RCLONE_CONFIG:-${HOME}/.config/rclone/rclone.conf}"
IDENTITY_FILE="${1:-}"

GDRIVE_REMOTE="${GDRIVE_REMOTE:-gdrive:}"
DRIVE_FOLDER_ID="${DRIVE_FOLDER_ID:-17yovLP4BK1L_2jJKXbu4H4F-1kiGXzQM}"
DRIVE_SECRETS_PATH="${DRIVE_SECRETS_PATH:-hermes-pg/secrets/secrets.age}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { printf '[encrypt-secrets] %s\n' "$*"; }
fail() { printf '[encrypt-secrets][FATAL] %s\n' "$*" >&2; exit 1; }

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

if [[ -z "$IDENTITY_FILE" ]]; then
    printf 'Usage: %s <identity-file>\n' "$0" >&2
    exit 1
fi
if [[ ! -f "$IDENTITY_FILE" ]]; then
    fail "identity file not found: ${IDENTITY_FILE}"
fi

command -v age-keygen >/dev/null 2>&1 || fail "age-keygen not found"
command -v rclone >/dev/null 2>&1     || fail "rclone not found"
command -v tar >/dev/null 2>&1        || fail "tar not found"

# Extract public key from identity
PUBLIC_KEY="$(age-keygen -y "$IDENTITY_FILE" 2>/dev/null)" || \
    fail "could not extract public key from ${IDENTITY_FILE}"
log "public recipient: ${PUBLIC_KEY}"

# ---------------------------------------------------------------------------
# Step 1: Package secrets
# ---------------------------------------------------------------------------

TEMP_DIR="$(mktemp -d)"
SECRETS_DIR="${TEMP_DIR}/secrets"
mkdir -p "$SECRETS_DIR"

if [[ -f "$HERMES_ENV_PATH" ]]; then
    cp "$HERMES_ENV_PATH" "${SECRETS_DIR}/.env"
    log "included ${HERMES_ENV_PATH}"
else
    log "WARN: ${HERMES_ENV_PATH} not found — .env not included"
fi
if [[ -f "$RCLONE_CONFIG" ]]; then
    cp "$RCLONE_CONFIG" "${SECRETS_DIR}/rclone.conf"
    log "included ${RCLONE_CONFIG}"
else
    log "WARN: ${RCLONE_CONFIG} not found — rclone config not included"
fi

if [[ -z "$(ls -A "$SECRETS_DIR" 2>/dev/null)" ]]; then
    fail "no secrets found to package"
fi

tar -cf "${TEMP_DIR}/secrets.tar" -C "$TEMP_DIR" secrets/ || fail "tar failed"
age -r "$PUBLIC_KEY" -o "${TEMP_DIR}/secrets.age" "${TEMP_DIR}/secrets.tar" || \
    fail "age encryption failed"
log "secrets.age encrypted"

# Wipe plaintext
rm -f "${TEMP_DIR}/secrets.tar"
rm -rf "${SECRETS_DIR}"

# ---------------------------------------------------------------------------
# Step 2: Upload to Drive
# ---------------------------------------------------------------------------

log "uploading to ${GDRIVE_REMOTE}${DRIVE_SECRETS_PATH} ..."
rclone copyto "${TEMP_DIR}/secrets.age" \
    "${GDRIVE_REMOTE}${DRIVE_SECRETS_PATH}" \
    --drive-root-folder-id "${DRIVE_FOLDER_ID}" || fail "rclone upload failed"
log "upload complete"

echo ""
echo "================================================"
echo " Secrets re-encrypted and uploaded"
echo "================================================"
echo " Identity:    ${IDENTITY_FILE}"
echo " Drive path:  ${GDRIVE_REMOTE}${DRIVE_SECRETS_PATH}"
echo "================================================"
