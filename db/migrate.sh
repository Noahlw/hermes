#!/usr/bin/env bash
# Wayfinder #47 — Hermes Postgres migration runner.
#
# Usage:
#   ./migrate.sh hermes|codebase_index|all
#
# Reads per-DB connection info from env:
#   HERMES_PGHOST (default 127.0.0.1)
#   HERMES_PGPORT (default 5433)
#   HERMES_PGUSER (default $USER, fallback "postgres")
#   HERMES_PGDB_HERMES          (default "hermes")
#   HERMES_PGDB_CODEBASE_INDEX  (default "codebase_index")
#
# This script is idempotent: each migration tracks its version in
# schema_migrations. Already-applied files are skipped.

set -euo pipefail

usage() {
    echo "usage: $0 hermes|codebase_index|all" >&2
    exit 2
}

[[ $# -ge 1 ]] || usage

target="$1"

HOST="${HERMES_PGHOST:-127.0.0.1}"
PORT="${HERMES_PGPORT:-5433}"
USER="${HERMES_PGUSER:-${USER:-postgres}}"
DB_HERMES="${HERMES_PGDB_HERMES:-hermes}"
DB_INDEX="${HERMES_PGDB_CODEBASE_INDEX:-codebase_index}"

if ! command -v psql >/dev/null 2>&1; then
    echo "ERROR: psql not in PATH. Install postgresql-client-16." >&2
    exit 1
fi

run_db() {
    local db="$1" label="$2"
    local dir
    dir="$(cd "$(dirname "$0")" && pwd)/${label}/migrations"
    if [[ ! -d "$dir" ]]; then
        echo "ERROR: migrations dir not found: $dir" >&2
        exit 1
    fi

    echo "==> [${label}] target ${HOST}:${PORT}/${db} as ${USER}"
    mapfile -t files < <(find "${dir}" -maxdepth 1 -type f -name '*.sql' | sort)
    if [[ ${#files[@]} -eq 0 ]]; then
        echo "    no migrations in ${dir}"
        return 0
    fi

    export PGHOST="$HOST"
    export PGPORT="$PORT"
    export PGUSER="$USER"
    export PGDATABASE="$db"

    for f in "${files[@]}"; do
        version="$(basename "$f" .sql)"
        # Skip if already recorded.
        already="$(psql -tA -X -c "SELECT 1 FROM schema_migrations WHERE version = '${version}' LIMIT 1;" 2>/dev/null || true)"
        if [[ "$already" == "1" ]]; then
            echo "    [skip] $version"
            continue
        fi
        echo "    [apply] $version"
        psql -v ON_ERROR_STOP=1 -X -1 -f "$f" >/dev/null
        psql -v ON_ERROR_STOP=1 -X -c "INSERT INTO schema_migrations (version) VALUES ('${version}');" >/dev/null
        echo "    [ok]    $version"
    done

    echo "==> [${label}] done"
}

case "$target" in
    hermes)
        run_db "$DB_HERMES" hermes
        ;;
    codebase_index)
        run_db "$DB_INDEX" codebase_index
        ;;
    all)
        run_db "$DB_HERMES" hermes
        echo
        run_db "$DB_INDEX" codebase_index
        ;;
    *)
        usage
        ;;
esac
