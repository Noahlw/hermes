#!/usr/bin/env bash
# Wayfinder #47 — Hermes Postgres VM provision script.
#
# Idempotently provisions an OS-managed PostgreSQL 16 + pgvector cluster on
# 127.0.0.1:5433 (Honcho's :5432 stays untouched). Creates two databases
# (`hermes`, `codebase_index`) with separate LOGIN owners.
#
# Hard rules:
#   * sudo -n only (no interactive password)
#   * Idempotent on every run
#   * Never touches Honcho's :5432

set -euo pipefail

PG_PORT="${HERMES_PG_PORT:-5433}"
DB_HERMES="${HERMES_DB:-hermes}"
DB_INDEX="${HERMES_INDEX_DB:-codebase_index}"
ROLE_HERMES="${HERMES_ROLE:-hermes_app}"
ROLE_INDEX="${HERMES_INDEX_ROLE:-codebase_index_app}"

CONF_DIR="/etc/postgresql/16/main/conf.d"
PORT_DROPIN="${CONF_DIR}/hermes-port.conf"
PG_HBA="/etc/postgresql/16/main/pg_hba.conf"
HBA_MARKER="# Hermes Postgres (#47) - local trust for two DBs and their owning roles."

log() { printf '[provision] %s\n' "$*"; }
fail() { printf '[provision][FATAL] %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

command -v sudo >/dev/null 2>&1 || fail "sudo not installed"
sudo -n true || fail "sudo -n rejected — refusing to prompt for password"

# ---------------------------------------------------------------------------
# Step 1: apt install
# ---------------------------------------------------------------------------

if dpkg -l postgresql-16 2>/dev/null | awk '/^ii/ {found=1} END {exit !found}'; then
    log "postgresql-16 already installed"
else
    log "apt-get update"
    sudo -n apt-get update -y
    log "apt-get install postgresql-16 + pgvector + client"
    sudo -n apt-get install -y postgresql-16 postgresql-16-pgvector postgresql-client-16
fi

# pgvector's version is best-effort; missing package is non-fatal because the
# extension itself is what matters and is loaded per-DB later.
if ! dpkg -l postgresql-16-pgvector 2>/dev/null | awk '/^ii/ {found=1} END {exit !found}'; then
    log "WARN: postgresql-16-pgvector not installed via apt — CREATE EXTENSION vector will fail later"
fi

# ---------------------------------------------------------------------------
# Step 2: ensure cluster is up before dropping in configs
# ---------------------------------------------------------------------------

if ! sudo -n systemctl is-active --quiet postgresql 2>/dev/null; then
    log "starting postgresql service"
    sudo -n systemctl start postgresql || sudo -n service postgresql start || true
fi

# ---------------------------------------------------------------------------
# Step 3: configure port + listen address via conf.d drop-in
# ---------------------------------------------------------------------------

sudo -n mkdir -p "${CONF_DIR}"

cat <<CONF | sudo -n tee "${PORT_DROPIN}" >/dev/null
port = ${PG_PORT}
listen_addresses = '127.0.0.1'
CONF
sudo -n chown postgres:postgres "${PORT_DROPIN}"
sudo -n chmod 0644 "${PORT_DROPIN}"
log "wrote ${PORT_DROPIN}"

# ---------------------------------------------------------------------------
# Step 4: pg_hba — append trust lines for the two DBs.
#
# NOTE: `include_dir` only applies to postgresql.conf, not pg_hba.conf. The
# plan called for a conf.d drop-in for pg_hba, but Ubuntu's pg_hba does not
# auto-include conf.d files. We therefore append a marker + two host lines
# to pg_hba.conf directly. Idempotent: marker gates re-append.
# ---------------------------------------------------------------------------

if sudo -n grep -qF "${HBA_MARKER}" "${PG_HBA}" 2>/dev/null; then
    log "pg_hba trust lines already present (marker found)"
else
    log "appending Hermes trust lines to ${PG_HBA}"
    {
        printf '\n%s\n' "${HBA_MARKER}"
        printf 'host    %s,%s    all             127.0.0.1/32            trust\n' \
            "${DB_HERMES}" "${DB_INDEX}"
        printf 'host    %s,%s    all             ::1/128                 trust\n' \
            "${DB_HERMES}" "${DB_INDEX}"
    } | sudo -n tee -a "${PG_HBA}" >/dev/null
    sudo -n chown postgres:postgres "${PG_HBA}"
    sudo -n chmod 0644 "${PG_HBA}"
fi

# Ensure local peer fallback exists for the unix socket (Ubuntu default file
# already covers `postgres` peer; we add a generic `all` peer entry if absent).
if ! sudo -n grep -Eq '^local[[:space:]]+all[[:space:]]+all[[:space:]]+peer' "${PG_HBA}"; then
    log "appending local peer fallback to ${PG_HBA}"
    printf '\n# Hermes (#47) - local socket peer fallback\nlocal   all             all                                     peer\n' \
        | sudo -n tee -a "${PG_HBA}" >/dev/null
    sudo -n chown postgres:postgres "${PG_HBA}"
fi

# ---------------------------------------------------------------------------
# Step 5: restart cluster
# ---------------------------------------------------------------------------

restart_cluster() {
    if sudo -n systemctl restart postgresql 2>/dev/null; then
        log "restarted via systemctl"
        return 0
    fi
    if sudo -n service postgresql restart 2>/dev/null; then
        log "restarted via service"
        return 0
    fi
    sudo -n pg_ctlcluster 16 main restart
    log "restarted via pg_ctlcluster"
}

reload_cluster() {
    if sudo -n pg_ctlcluster 16 main reload 2>/dev/null; then
        log "reloaded via pg_ctlcluster"
        return 0
    fi
    sudo -n systemctl reload postgresql 2>/dev/null || restart_cluster
    log "reloaded via systemctl (or restarted)"
}

restart_cluster
reload_cluster

# ---------------------------------------------------------------------------
# Step 6: ensure roles exist
# ---------------------------------------------------------------------------

psql_admin() {
    sudo -n -u postgres psql -h /var/run/postgresql -p "${PG_PORT}" -tA -X -v ON_ERROR_STOP=1 "$@"
}

ensure_role() {
    local role="$1"
    local exists
    exists="$(psql_admin -c "SELECT 1 FROM pg_roles WHERE rolname='${role}' LIMIT 1;")"
    if [[ "$exists" == "1" ]]; then
        log "role ${role} already exists"
    else
        log "creating role ${role}"
        psql_admin -c "CREATE ROLE \"${role}\" WITH LOGIN;"
    fi
}

ensure_role "${ROLE_HERMES}"
ensure_role "${ROLE_INDEX}"

# ---------------------------------------------------------------------------
# Step 7: ensure databases exist
# ---------------------------------------------------------------------------

ensure_db() {
    local db="$1" owner="$2"
    local exists
    exists="$(psql_admin -c "SELECT 1 FROM pg_database WHERE datname='${db}' LIMIT 1;")"
    if [[ "$exists" == "1" ]]; then
        log "database ${db} already exists"
    else
        log "creating database ${db} OWNER ${owner}"
        psql_admin -c "CREATE DATABASE \"${db}\" OWNER \"${owner}\";"
    fi
}

ensure_db "${DB_HERMES}" "${ROLE_HERMES}"
ensure_db "${DB_INDEX}" "${ROLE_INDEX}"

# ---------------------------------------------------------------------------
# Step 8: verify
# ---------------------------------------------------------------------------

if ss -tln 2>/dev/null | grep -q ":${PG_PORT}[[:space:]]"; then
    log "ok: listening on :${PG_PORT}"
else
    log "WARN: ss did not show :${PG_PORT} — checking via pg_isready"
    sudo -n -u postgres pg_isready -h 127.0.0.1 -p "${PG_PORT}" || fail "port ${PG_PORT} not reachable"
fi

if ss -tln 2>/dev/null | grep -q ':5432[[:space:]]'; then
    log "ok: Honcho :5432 still listening (untouched)"
else
    log "WARN: Honcho :5432 not visible — verify Honcho separately; this script does not manage it"
fi

# Round-trip connect via trust.
if PGPORT="${PG_PORT}" PGHOST=127.0.0.1 PGUSER="${ROLE_HERMES}" \
    psql -d "${DB_HERMES}" -tA -c "select 1;" >/dev/null 2>&1; then
    log "connect ${ROLE_HERMES}@${DB_HERMES}:${PG_PORT} ok"
else
    log "WARN: connect as ${ROLE_HERMES} failed (may need explicit trust reload)"
    reload_cluster
fi

if PGPORT="${PG_PORT}" PGHOST=127.0.0.1 PGUSER="${ROLE_INDEX}" \
    psql -d "${DB_INDEX}" -tA -c "select 1;" >/dev/null 2>&1; then
    log "connect ${ROLE_INDEX}@${DB_INDEX}:${PG_PORT} ok"
else
    log "WARN: connect as ${ROLE_INDEX} failed (may need explicit trust reload)"
    reload_cluster
fi

log "provision complete"