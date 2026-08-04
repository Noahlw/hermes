#!/usr/bin/env bash
# Wayfinder #47 — Hermes Postgres smoke script.
#
# Runs against the live 127.0.0.1:5433 cluster provisioned by
# scripts/vm/provision-hermes-postgres.sh. Idempotent: each check inserts
# then deletes or upserts a uniquely-named probe row, so re-runs work.
#
# Output: one line per check (e.g. `a:ok`) ending with `ALL_PASS` or
# `FAIL:<letters>` for any failed checks.

set -u

PGHOST="${HERMES_PGHOST:-127.0.0.1}"
PGPORT="${HERMES_PGPORT:-5433}"
DB_HERMES="${HERMES_PGDB_HERMES:-hermes}"
DB_INDEX="${HERMES_PGDB_CODEBASE_INDEX:-codebase_index}"
USER_HERMES="${HERMES_ROLE:-hermes_app}"
USER_INDEX="${HERMES_INDEX_ROLE:-codebase_index_app}"

PROBE_ID="smoke-$(date -u +%Y%m%dT%H%M%SZ)-$$"

FAILED_KEYS=()
declare -A RESULTS

ok()  { RESULTS["$1"]="ok"; printf '%s:ok\n' "$1"; }
bad() { RESULTS["$1"]="FAIL"; printf '%s:FAIL\n' "$1"; FAILED_KEYS+=("$1"); }

run_hermes() {
    PGPORT="$PGPORT" PGHOST="$PGHOST" PGUSER="$USER_HERMES" \
        psql -v ON_ERROR_STOP=1 -X -q -tA "$DB_HERMES" "$@"
}
run_index() {
    PGPORT="$PGPORT" PGHOST="$PGHOST" PGUSER="$USER_INDEX" \
        psql -v ON_ERROR_STOP=1 -X -q -tA "$DB_INDEX" "$@"
}

# ---- a: connect hermes ----------------------------------------------------
if run_hermes -c 'select 1' >/dev/null 2>&1; then ok a; else bad a; fi

# ---- b: connect codebase_index -------------------------------------------
if run_index -c 'select 1' >/dev/null 2>&1; then ok b; else bad b; fi

# ---- c: audit_events insert + select -------------------------------------
C_OUT="$(run_hermes <<SQL | head -n1
INSERT INTO audit_events (occurred_at, actor, action, payload, provenance)
VALUES (now(), 'smoke', 'smoke.test', jsonb_build_object('probe','$PROBE_ID'),
        jsonb_build_object('script','smoke-hermes-postgres.sh'))
RETURNING id;
SQL
)"
if [[ "$C_OUT" =~ ^[0-9]+$ ]] && \
   run_hermes -c "SELECT action FROM audit_events WHERE id=$C_OUT" 2>/dev/null | grep -q '^smoke.test$'; then
    ok c
else
    bad c
fi

# ---- d: research_evidence insert + select --------------------------------
D_OUT="$(run_hermes <<SQL | head -n1
INSERT INTO research_evidence
    (topic, claim, source_uri, retrieved_at, excerpt, excerpt_hash, confidence, sensitivity)
VALUES ('smoke', 'smoke claim $PROBE_ID',
        'smoke://test/$PROBE_ID',
        now(), 'excerpt $PROBE_ID',
        md5('$PROBE_ID'), 0.5, 'public')
RETURNING id;
SQL
)"
if [[ "$D_OUT" =~ ^[0-9]+$ ]] && \
   run_hermes -c "SELECT claim FROM research_evidence WHERE id=$D_OUT" 2>/dev/null \
        | grep -q "smoke claim $PROBE_ID"; then
    ok d
else
    bad d
fi

# ---- e: digest_allowlists tech_news --------------------------------------
E_OUT="$(run_hermes <<SQL | head -n1
INSERT INTO digest_allowlists (topic, enabled, config)
VALUES ('tech_news', false, jsonb_build_object('probe','$PROBE_ID'))
ON CONFLICT (topic) DO UPDATE SET enabled = EXCLUDED.enabled,
                                  config = EXCLUDED.config
RETURNING id;
SQL
)"
run_hermes -c "UPDATE digest_allowlists SET enabled=true WHERE id=$E_OUT" >/dev/null 2>&1
ENABLED="$(run_hermes -c "SELECT enabled::text FROM digest_allowlists WHERE topic='tech_news';")"
if [[ "$ENABLED" == "t" || "$ENABLED" == "true" ]]; then ok e; else bad e; fi

# ---- f: repos insert -----------------------------------------------------
F_OUT="$(run_index <<SQL | head -n1
INSERT INTO repos (owner_name, default_branch)
VALUES ('acme/widget', 'main')
ON CONFLICT (owner_name) DO UPDATE SET default_branch = EXCLUDED.default_branch
RETURNING id;
SQL
)"
if [[ "$F_OUT" =~ ^[0-9]+$ ]]; then ok f; else bad f; fi

# ---- g: files insert -----------------------------------------------------
G_OUT="$(run_index <<SQL | head -n1
INSERT INTO files (repo_id, path, commit_sha)
VALUES ($F_OUT, 'README.md', 'abc123')
ON CONFLICT (repo_id, commit_sha, path) DO UPDATE SET path = EXCLUDED.path
RETURNING id;
SQL
)"
if [[ "$G_OUT" =~ ^[0-9]+$ ]]; then ok g; else bad g; fi

# ---- h: chunks insert + FTS ----------------------------------------------
H_OUT="$(run_index <<SQL | head -n1
INSERT INTO chunks (file_id, chunk_index, content, content_sha)
VALUES ($G_OUT, 1, 'Postgres is a powerful relational database.',
        '$PROBE_ID')
ON CONFLICT (file_id, chunk_index) DO UPDATE SET content = EXCLUDED.content
RETURNING id;
SQL
)"
FTS_COUNT="$(run_index -c \
    "SELECT count(*) FROM chunks WHERE tsv @@ to_tsquery('english','postgres');")"
if [[ "$FTS_COUNT" =~ ^[0-9]+$ ]] && (( FTS_COUNT >= 1 )); then
    ok h
else
    bad h
fi

# ---- i: chunk_embeddings 768-dim zero vector -----------------------------
run_index -c "DELETE FROM chunk_embeddings WHERE chunk_id=$H_OUT;" >/dev/null 2>&1
ZERO_VECTOR="$(printf '0,%.0s' {1..767}; printf '0')"
I_OUT="$(run_index <<SQL | head -n1
INSERT INTO chunk_embeddings (chunk_id, model, dims, embedding, content_sha)
VALUES ($H_OUT, 'nomic-embed-text', 768,
        string_to_array('$ZERO_VECTOR', ',')::real[],
        '$PROBE_ID')
RETURNING chunk_id;
SQL
)" 2>&1
EMB_DIMS="$(run_index -c \
    "SELECT array_length(string_to_array(embedding::text, ','), 1) FROM chunk_embeddings WHERE chunk_id=$H_OUT;" 2>/dev/null | tr -d ' ')"
# Real verification via vector_dims()
REAL_DIMS="$(run_index -c \
    "SELECT vector_dims(embedding) FROM chunk_embeddings WHERE chunk_id=$H_OUT;" 2>/dev/null | tr -d ' ')"
if [[ "$REAL_DIMS" == "768" ]]; then ok i; else bad i; fi

# ---- j: Honcho :5432 still listening -------------------------------------
# ---- j: Honcho API /health (self-hosted :8000; Docker-era :5432 gone) ------
J_OK=0
if command -v curl >/dev/null 2>&1 && \
        curl -fsS --max-time 5 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    J_OK=1
else
    # curl-less fallback: /dev/tcp, but require an HTTP 200 response so a
    # random listener on :8000 cannot satisfy the gate.
    J_STATUS="$(timeout 5 bash -c 'exec 3<>/dev/tcp/127.0.0.1/8000; printf "GET /health HTTP/1.0\r\n\r\n" >&3; IFS= read -r line <&3; printf "%s" "$line"' 2>/dev/null)"
    case "$J_STATUS" in *200*) J_OK=1 ;; *) J_OK=0 ;; esac
fi
if (( J_OK )); then ok j; else bad j; fi

# ---- k: schema_meta dim=768 ----------------------------------------------
K_DIM="$(run_index -c "SELECT (value->>'dim') FROM schema_meta WHERE key='embedding_default_dim';" 2>/dev/null | tr -d ' ')"
if [[ "$K_DIM" == "768" ]]; then ok k; else bad k; fi

# ---- l: schema_meta model=nomic-embed-text -------------------------------
L_MODEL="$(run_index -c "SELECT (value->>'model') FROM schema_meta WHERE key='embedding_default_model';" 2>/dev/null | tr -d ' ')"
if [[ "$L_MODEL" == "nomic-embed-text" ]]; then ok l; else bad l; fi

# ---- summary -------------------------------------------------------------
if (( ${#FAILED_KEYS[@]} == 0 )); then
    echo "ALL_PASS"
    exit 0
fi
FAIL_LIST=""
for k in "${FAILED_KEYS[@]}"; do
    FAIL_LIST+="$k"
done
echo "FAIL:$FAIL_LIST"
exit 1