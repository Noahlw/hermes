# Provision Hermes Postgres + codebase-index Postgres (#47)

**Wayfinder ticket:** [#47](https://github.com/Noahlw/hermes/issues/47)  
**Parent:** [#38](https://github.com/Noahlw/hermes/issues/38) · follow-up from [#41](https://github.com/Noahlw/hermes/issues/41) MEM-3/4  
**Branch:** `task/47-provision-postgres`  
**Status:** locks committed `822d301` (2026-07-27); implementation plan next

## Locked decisions

| ID | Decision | Consequence |
|---|---|---|
| **MEM-3** (from #41) | Two-database split | Hermes DB ≠ codebase index DB |
| **MEM-4** (from #41) | Both are Postgres; index uses pgvector + FTS | Honcho Postgres untouched |
| **PG-1** | **One dedicated Hermes Postgres + two logical DBs** | New instance (not Honcho’s `:5432`). Databases `hermes` and `codebase_index` with separate roles. Suggested bind `127.0.0.1:5433` to avoid colliding with Honcho. |
| **PG-2** | **systemd + apt Postgres (native)** | Hermes Postgres is OS-managed (`postgresql` + pgvector), not Docker. Matches “Hermes-used VM” ownership; Honcho may remain Docker. |
| **PG-3** | **Listen `127.0.0.1:5433`** | Localhost-only; no Tailscale Postgres exposure. Avoids Honcho’s `:5432`. |
| **PG-4** | **Trust / peer auth like Honcho** | Local `pg_hba` trust (or equivalent peer) for Hermes Postgres on `127.0.0.1`. Separate DB names still; role passwords not required for V1 local access. Rotate/harden later if exposure changes. |
| **PG-5** | **Full schemas in #47** | Not provision-only. #47 lands Hermes canonical schema **and** codebase-index schema (tables/extensions/migrations), not empty shells. |
| **PG-6** | **Core V1 memory domains only** | Hermes DB: audit, research evidence, persona/task scope, session briefs, digest artifacts (+ allowlists). Codebase index DB: catalog, paths/symbols/chunks, FTS, embeddings, revision cursors (#40). Out: email/news corpora, PopIdea. |
| **PG-7** | **SQL migrations in this Hermes repo** | `db/hermes/migrations/*.sql` + `db/codebase_index/migrations/*.sql`; applied via `psql` runner on the VM. No Alembic/ORM required for #47. |
| **PG-8** | **Embeddings configurable; default dim 768** | Index schema includes embedding storage + model/dim metadata. First migration defaults to 768 (current Ollama `nomic-embed-text`). #43 may change default via later migration. |
| **PG-9** | **Hybrid close for #47** | Close after SQL migrations in repo + live VM Postgres on `:5433` with both DBs migrated + config wired + smoke insert/select. Not blocked on full indexer or #48 Drive restore. |

## Observed VM baseline (2026-07-27)

| Item | State |
|---|---|
| Honcho Postgres | `pgvector/pgvector:pg15` on `127.0.0.1:5432` — leave alone |
| Hermes DB config | No `hermes_db` / `codebase_index_db` keys in `config.yaml` yet |
| Disk | ~104 GB free on `/` |
