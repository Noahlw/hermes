#!/usr/bin/env bash
# Wayfinder #50 — Age key bootstrap + encrypted secrets upload.
#
# Generates an age identity key, packages minimal Hermes runtime secrets,
# encrypts them, and uploads to Drive under hermes-pg/secrets/secrets.age.
#
# Usage:
#   ./key-bootstrap.sh [identity-file-path]
#
# Default identity path: ./hermes-age-key.txt (current directory)
# The identity (private) key file is NEVER uploaded to Drive or committed.
#
# Prerequisites:
#   - age installed (https://github.com/FiloSottile/age)
#   - rclone configured with "gdrive:" remote
#   - Hermes .env file at HERMES_ENV_PATH or default location

set -euo pipefail

# ---------------------------------------------------------------------------
# Configurable defaults
# ---------------------------------------------------------------------------
HERMES_HOME="${HERMES_HOME:-/home/ubuntu/.hermes}"
HERMES_ENV_PATH="${HERMES_ENV_PATH:-${HERMES_HOME}/.env}"
RCLONE_CONFIG="${RCLONE_CONFIG:-${HOME}/.config/rclone/rclone.conf}"
IDENTITY_FILE="${1:-${PWD}/hermes-age-key.txt}"

GDRIVE_REMOTE="${GDRIVE_REMOTE:-gdrive:}"
DRIVE_FOLDER_ID="${DRIVE_FOLDER_ID:-17yovLP4BK1L_2jJKXbu4H4F-1kiGXzQM}"
DRIVE_SECRETS_PATH="${DRIVE_SECRETS_PATH:-hermes-pg/secrets/secrets.age}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { printf '[key-bootstrap] %s\n' "$*"; }
fail() { printf '[key-bootstrap][FATAL] %s\n' "$*" >&2; exit 1; }

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

command -v age-keygen >/dev/null 2>&1 || fail "age-keygen not found — install age (brew install age or apt install age)"
command -v rclone >/dev/null 2>&1 || fail "rclone not found — install rclone"
command -v tar >/dev/null 2>&1 || fail "tar not found"

# Test rclone remote
if ! rclone lsd "${GDRIVE_REMOTE}" --drive-root-folder-id "${DRIVE_FOLDER_ID}" >/dev/null 2>&1; then
    fail "cannot access gdrive: remote — check rclone config and folder ID"
fi

# ---------------------------------------------------------------------------
# Step 1: Generate age identity (if not already present)
# ---------------------------------------------------------------------------

if [[ -f "$IDENTITY_FILE" ]]; then
    log "identity file already exists at ${IDENTITY_FILE} — using existing key"
else
    log "generating new age identity at ${IDENTITY_FILE}"
    age-keygen -o "$IDENTITY_FILE" 2>/dev/null || fail "age-keygen failed"
    chmod 0400 "$IDENTITY_FILE"
    log "identity file generated — KEEP THIS FILE SAFE (never upload to Drive)"
fi

# Extract the public (recipient) key from the identity file
PUBLIC_KEY="$(age-keygen -y "$IDENTITY_FILE" 2>/dev/null)" || fail "could not extract public key from ${IDENTITY_FILE}"
log "public recipient: ${PUBLIC_KEY}"

# ---------------------------------------------------------------------------
# Step 2: Package secrets into temp directory
# ---------------------------------------------------------------------------

TEMP_DIR="$(mktemp -d)"
log "working in temporary directory: ${TEMP_DIR}"

SECRETS_DIR="${TEMP_DIR}/secrets"
mkdir -p "$SECRETS_DIR"

# Hermes .env file
if [[ -f "$HERMES_ENV_PATH" ]]; then
    cp "$HERMES_ENV_PATH" "${SECRETS_DIR}/.env"
    log "included ${HERMES_ENV_PATH}"
else
    log "WARN: ${HERMES_ENV_PATH} not found — .env not included in archive"
fi

# rclone config
if [[ -f "$RCLONE_CONFIG" ]]; then
    cp "$RCLONE_CONFIG" "${SECRETS_DIR}/rclone.conf"
    log "included ${RCLONE_CONFIG}"
else
    log "WARN: ${RCLONE_CONFIG} not found — rclone config not included in archive"
fi

# Verify there's at least something to encrypt
if [[ -z "$(ls -A "$SECRETS_DIR" 2>/dev/null)" ]]; then
    fail "no secrets found to package — checked HERMES_ENV_PATH and RCLONE_CONFIG"
fi

# Create tar archive (no root-owned files since we cp'd as the running user)
tar -cf "${TEMP_DIR}/secrets.tar" -C "$TEMP_DIR" secrets/ || fail "tar failed"

# ---------------------------------------------------------------------------
# Step 3: Encrypt with age
# ---------------------------------------------------------------------------

age -r "$PUBLIC_KEY" -o "${TEMP_DIR}/secrets.age" "${TEMP_DIR}/secrets.tar" || fail "age encryption failed"
log "encrypted secrets archive created (${TEMP_DIR}/secrets.age)"

# Wipe the plaintext tar
rm -f "${TEMP_DIR}/secrets.tar"
rm -rf "${SECRETS_DIR}"

# ---------------------------------------------------------------------------
# Step 4: Upload to Drive
# ---------------------------------------------------------------------------

log "uploading to ${GDRIVE_REMOTE}${DRIVE_SECRETS_PATH} ..."
rclone copyto "${TEMP_DIR}/secrets.age" \
    "${GDRIVE_REMOTE}${DRIVE_SECRETS_PATH}" \
    --drive-root-folder-id "${DRIVE_FOLDER_ID}" || fail "rclone upload failed"
log "upload complete"

# ---------------------------------------------------------------------------
# Step 5: Cleanup (via trap) + success
# ---------------------------------------------------------------------------

echo ""
echo "================================================"
echo " Bootstrap complete"
echo "================================================"
echo " Identity file: ${IDENTITY_FILE}"
echo " Recipient:     ${PUBLIC_KEY}"
echo " Drive path:    ${GDRIVE_REMOTE}${DRIVE_SECRETS_PATH}"
echo ""
echo " IMPORTANT: Store the identity file securely."
echo " It is your ONLY way to decrypt the secrets archive."
echo " It has NOT been uploaded to Drive or committed to git."
echo "================================================"
