# Provision Hermes Postgres (#47) Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a dedicated systemd/apt Postgres 16 on `127.0.0.1:5433` with logical DBs `hermes` and `codebase_index`, land core V1 SQL schemas + migrations in this repo, wire Hermes config, smoke-test, and close #47 under PG-9 hybrid close.

**Architecture:** One OS-managed Postgres cluster (not Docker, not Honcho’s `:5432`). Two databases on that cluster. Versioned SQL under `db/` applied by a `psql` runner. Schemas cover PG-6 domains only; no indexer pipeline and no Drive backup (#48).

**Tech Stack:** Ubuntu 24.04 apt `postgresql-16` + `postgresql-16-pgvector`, `psql`, bash runner, Hermes `config.yaml` / `.env` on VM, GitHub issue #47.

## Global Constraints

- Locks: PG-1…9 in [`docs/research/postgres-provisioning-47.md`](docs/research/postgres-provisioning-47.md) (commit `822d301`).
- Do not modify Honcho compose or its Postgres on `:5432`.
- Listen only `127.0.0.1:5433` (PG-3). Trust/peer local auth (PG-4).
- Default embedding dim **768** with model/dim metadata columns (PG-8).
- No email/news/PopIdea tables (PG-6).
- Secrets: never print `.env` values; report key names only.
- Branch: `task/47-provision-postgres`. Push to `github` remote.
- SSH: `ubuntu@100.79.87.93` with `~/.ssh/hermes-vm-leaked`; use `sudo -n` only (no password hang).

## File Structure & Changes

| Path | Responsibility |
|---|---|
| `db/hermes/migrations/0001_init.sql` | Hermes DB core tables |
| `db/codebase_index/migrations/0001_init.sql` | Codebase index tables + `vector` + FTS |
| `db/migrate.sh` | Idempotent `psql` migration runner for both DBs |
| `db/README.md` | How to apply migrations on the VM |
| `scripts/vm/provision-hermes-postgres.sh` | Apt install, cluster port 5433, create DBs/roles, `pg_hba`, enable extensions |
| `scripts/vm/smoke-hermes-postgres.sh` | Connect + sample insert/select both DBs |
| Hermes VM `/etc/postgresql/16/main/postgresql.conf` (or conf.d) | `port=5433`, listen `127.0.0.1` |
| Hermes VM `pg_hba.conf` | trust/peer for local `127.0.0.1/32` to both DBs |
| VM `~/.hermes/config.yaml` + `.env` | Connection keys for both DBs (no passwords if trust) |
| `docs/use-case-specification.md` §6.5 | Record live Hermes Postgres |
| `docs/research/postgres-provisioning-47.md` | Close checklist + verify stamp |
| GitHub #47 | Comment + close |

## What Already Exists

- Decision locks PG-1…9 and glossary terms in `CONTEXT.md`.
- Honcho already proves `pgvector` works on this VM (Docker `:5432`) — leave it.
- Apt packages available: `postgresql-16`, `postgresql-16-pgvector` (0.6.0).
- #40 IDX locks define catalog/soft-delete/webhook cursor needs for the index schema.
- AgentMemory-style disable stamps pattern for reversible ops (not needed unless uninstall).

## Not In Scope

- Drive dump cron (#48).
- Full codebase indexer / webhook worker / Tree-sitter pipeline.
- Changing embedding provider (#43) beyond schema default dim 768.
- Honcho Postgres changes.
- Email/news/PopIdea tables.
- Exposing Postgres on Tailscale.

## ASCII Diagrams

```text
VM localhost
  :5432  Honcho Docker Postgres (untouched)
  :5433  systemd postgresql-16
           ├── DB hermes
           │     audit_events, research_evidence, persona_task_scopes,
           │     session_briefs, digest_artifacts, digest_allowlists
           └── DB codebase_index
                 repos, repo_refs, files, symbols, chunks,
                 chunk_embeddings, sync_cursors, schema_meta

Repo: db/*/migrations/*.sql  --migrate.sh-->  :5433
Hermes config.yaml  -->  connection strings (host/port/db/user)
```

```text
Smoke flow
  psql hermes: INSERT audit_events -> SELECT
  psql codebase_index: INSERT repos + chunks -> FTS query + vector dim check
```

## Failure Modes & Gaps

- Apt `postgresql` meta-package may try default port 5432 — must configure **5433 before first start** or alter and restart; verify no clash with Honcho.
- `postgresql-16-pgvector` must match major 16; enable `CREATE EXTENSION vector` inside `codebase_index` (and only there unless Hermes DB also needs it — it does not per PG-6).
- Trust auth means any local process can connect — acceptable under PG-4; document in ops notes.
- Schema is V1-complete for domains but indexer code may still need ALTERs later — migration numbering must stay monotonic.
- `#47` acceptance text mentions “gateway migrations” / “index pipeline” — rewrite acceptance in the closing comment to PG-9 smoke bar.

## Parallelization / Worktree Strategy

- Single branch `task/47-provision-postgres` in current checkout.
- Order: **schema+runner in repo → VM provision script → apply migrations → wire config → smoke → docs/issue close**.
- Schema design and VM provision script authoring can be drafted in parallel in one agent, but VM apply waits on committed SQL.

---

### Task 1: Hermes DB migration `0001_init.sql`

**Files:**
- Create: `db/hermes/migrations/0001_init.sql`
- Create: `db/hermes/migrations/.gitkeep` only if needed (prefer real SQL)

**Interfaces:**
- Produces tables usable by smoke script and later Hermes services
- Consumes: PG-6 Hermes domain list; provenance fields from #41 research note

- [ ] **Step 1: Write failing smoke expectation doc in plan checklist** (no code test harness yet)

Document required tables/columns for Task 5 smoke.

- [ ] **Step 2: Author `0001_init.sql`**

Must create (names exact):

1. `schema_migrations` (`version TEXT PRIMARY KEY`, `applied_at TIMESTAMPTZ NOT NULL DEFAULT now()`)
2. `audit_events` — append-only: `id BIGSERIAL PK`, `occurred_at TIMESTAMPTZ NOT NULL`, `actor TEXT`, `persona_id TEXT`, `task_id TEXT`, `action TEXT NOT NULL`, `payload JSONB NOT NULL DEFAULT '{}'`, `provenance JSONB NOT NULL DEFAULT '{}'`
3. `research_evidence` — `id BIGSERIAL PK`, `topic TEXT NOT NULL`, `claim TEXT NOT NULL`, `source_uri TEXT NOT NULL`, `retrieved_at TIMESTAMPTZ NOT NULL`, `excerpt TEXT`, `excerpt_hash TEXT`, `confidence REAL`, `sensitivity TEXT NOT NULL DEFAULT 'public' CHECK (sensitivity IN ('public','private'))`, `persona_id TEXT`, `task_id TEXT`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `supersedes BIGINT REFERENCES research_evidence(id)`
4. `persona_task_scopes` — `id BIGSERIAL PK`, `persona_id TEXT NOT NULL`, `task_id TEXT NOT NULL`, `visibility TEXT NOT NULL CHECK (visibility IN ('private','shared'))`, `metadata JSONB NOT NULL DEFAULT '{}'`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `UNIQUE (persona_id, task_id)`
5. `session_briefs` — `id BIGSERIAL PK`, `task TEXT NOT NULL`, `repos TEXT[]`, `brief_markdown TEXT NOT NULL`, `citations JSONB NOT NULL DEFAULT '[]'`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
6. `digest_artifacts` — `id BIGSERIAL PK`, `kind TEXT NOT NULL`, `title TEXT NOT NULL`, `body_markdown TEXT NOT NULL`, `topics TEXT[]`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
7. `digest_allowlists` — `id BIGSERIAL PK`, `topic TEXT NOT NULL UNIQUE`, `enabled BOOLEAN NOT NULL DEFAULT true`, `config JSONB NOT NULL DEFAULT '{}'`

Use `IF NOT EXISTS` where safe. No `vector` extension in Hermes DB.

- [ ] **Step 3: Commit**

Message: `feat(#47): add Hermes DB init migration`

---

### Task 2: Codebase index migration `0001_init.sql`

**Files:**
- Create: `db/codebase_index/migrations/0001_init.sql`

**Interfaces:**
- Aligns with #40 catalog / soft-delete / cursor needs
- Default embedding dim 768 (PG-8)

- [ ] **Step 1: Author `0001_init.sql`**

Must:

1. `CREATE EXTENSION IF NOT EXISTS vector;`
2. `schema_migrations` (same shape as Hermes DB)
3. `schema_meta` — `key TEXT PK`, `value JSONB NOT NULL` — seed row `embedding_default_dim = 768`, `embedding_default_model = 'nomic-embed-text'`
4. `repos` — catalog: `id BIGSERIAL PK`, `owner_name TEXT NOT NULL` (format `owner/name`), `default_branch TEXT NOT NULL`, `status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked'))`, `revoked_at TIMESTAMPTZ`, `purge_after TIMESTAMPTZ`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `UNIQUE (owner_name)`
5. `repo_refs` — `id BIGSERIAL PK`, `repo_id BIGINT NOT NULL REFERENCES repos(id)`, `ref_name TEXT NOT NULL`, `pinned_sha TEXT`, `UNIQUE (repo_id, ref_name)`
6. `files` — `id BIGSERIAL PK`, `repo_id BIGINT NOT NULL REFERENCES repos(id)`, `ref_id BIGINT REFERENCES repo_refs(id)`, `path TEXT NOT NULL`, `language TEXT`, `content_sha TEXT`, `commit_sha TEXT NOT NULL`, `UNIQUE (repo_id, commit_sha, path)`
7. `symbols` — `id BIGSERIAL PK`, `file_id BIGINT NOT NULL REFERENCES files(id)`, `name TEXT NOT NULL`, `kind TEXT`, `start_line INT`, `end_line INT`, `signature TEXT`
8. `chunks` — `id BIGSERIAL PK`, `file_id BIGINT NOT NULL REFERENCES files(id)`, `chunk_index INT NOT NULL`, `start_line INT`, `end_line INT`, `content TEXT NOT NULL`, `content_sha TEXT NOT NULL`, `tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED`, `UNIQUE (file_id, chunk_index)`
9. GIN index on `chunks.tsv`
10. `chunk_embeddings` — `chunk_id BIGINT PK REFERENCES chunks(id) ON DELETE CASCADE`, `model TEXT NOT NULL`, `dims INT NOT NULL`, `embedding vector(768) NOT NULL`, `content_sha TEXT NOT NULL`
11. `sync_cursors` — webhook/reconcile: `id BIGSERIAL PK`, `repo_id BIGINT NOT NULL REFERENCES repos(id)`, `ref_name TEXT NOT NULL`, `last_before_sha TEXT`, `last_after_sha TEXT`, `last_success_at TIMESTAMPTZ`, `UNIQUE (repo_id, ref_name)`

- [ ] **Step 2: Commit**

Message: `feat(#47): add codebase_index DB init migration`

---

### Task 3: Migration runner + README

**Files:**
- Create: `db/migrate.sh`
- Create: `db/README.md`

**Interfaces:**
- Consumes: `HERMES_PGHOST` (default `127.0.0.1`), `HERMES_PGPORT` (default `5433`), `HERMES_PGUSER` (default `ubuntu` or `postgres`), DB names `hermes` / `codebase_index`
- Applies files in sorted order; records versions in `schema_migrations`

- [ ] **Step 1: Implement `db/migrate.sh`**

Behavior:

- Args: `migrate.sh hermes|codebase_index|all`
- For each pending `NNNN_*.sql` not in `schema_migrations`, run inside a transaction when possible; on success `INSERT INTO schema_migrations(version) VALUES ('NNNN_name')`
- Exit non-zero on failure; print applied versions
- Use `psql` with `ON_ERROR_STOP=1`

- [ ] **Step 2: Write `db/README.md`**

Document port 5433, DB names, trust auth, how to run migrate + smoke, pointer to provision script.

- [ ] **Step 3: Commit**

Message: `feat(#47): add psql migration runner`

---

### Task 4: VM provision script (apt + cluster on 5433)

**Files:**
- Create: `scripts/vm/provision-hermes-postgres.sh`

**Interfaces:**
- Produces: listening `127.0.0.1:5433`, roles/DBs exist, `ubuntu` (or `hermes`) can connect via trust from localhost

- [ ] **Step 1: Author provision script**

Must:

1. `sudo -n apt-get update && sudo -n apt-get install -y postgresql-16 postgresql-16-pgvector postgresql-client-16`
2. Configure cluster to **port 5433** and `listen_addresses = '127.0.0.1'` (use `conf.d` drop-in under `/etc/postgresql/16/main/conf.d/hermes-port.conf` if available)
3. `pg_hba.conf`: allow `host hermes,codebase_index all 127.0.0.1/32 trust` (and local peer as needed)
4. `sudo -n systemctl restart postgresql` (or `postgresql@16-main`)
5. Create roles if needed (e.g. `hermes_app`, `codebase_index_app` owning respective DBs) — passwords optional under PG-4; ownership still separate
6. `CREATE DATABASE hermes OWNER ...;` `CREATE DATABASE codebase_index OWNER ...;`
7. Verify `ss -tln | grep 5433` and Honcho still on 5432

Idempotent: re-run safe if DBs exist.

- [ ] **Step 2: Run on VM via SSH**

Execute the script; capture outputs. If `sudo -n` fails, stop and report (do not hang).

- [ ] **Step 3: Commit script**

Message: `feat(#47): add VM Hermes Postgres provision script`

---

### Task 5: Apply migrations + smoke + wire config

**Files:**
- Create: `scripts/vm/smoke-hermes-postgres.sh`
- Modify on VM: `/home/ubuntu/.hermes/config.yaml` (and `.env` key names only)
- Modify: `docs/use-case-specification.md` §6.5
- Modify: `docs/research/postgres-provisioning-47.md`

**Interfaces:**
- Config keys (exact): under `databases:` or top-level as decided in script comments:

```yaml
databases:
  hermes:
    host: 127.0.0.1
    port: 5433
    name: hermes
    user: hermes_app   # or ubuntu
  codebase_index:
    host: 127.0.0.1
    port: 5433
    name: codebase_index
    user: codebase_index_app
```

- [ ] **Step 1: Copy migrations to VM or run from git clone path**

Prefer: clone/pull this repo on VM **or** `scp` `db/` then `./db/migrate.sh all`.

- [ ] **Step 2: Run smoke script**

Must assert:

1. Connect both DBs
2. Insert one `audit_events` row; select it back
3. Insert one `repos` + `chunks` row; `to_tsvector` / FTS query returns row
4. `chunk_embeddings.embedding` accepts a 768-dim zero vector (or small fixture)
5. Honcho `:5432` still up
6. Print `ALL_PASS`

- [ ] **Step 3: Wire config.yaml** (backup `config.yaml.bak.<TS>` first)

- [ ] **Step 4: Update docs §6.5 + research close checklist**

- [ ] **Step 5: Commit docs + smoke script; push**

Message: `docs(#47): record live Postgres provision and smoke`

---

### Task 6: Close #47

**Files:** GitHub only (+ final doc verify stamp if needed)

- [ ] **Step 1: Comment on #47** with PG-1…9 summary, commit SHAs, smoke table, follow-ups (#48, indexer implementation, #43 dim change)

- [ ] **Step 2: `gh issue close 47 --reason completed`**

- [ ] **Step 3: Open PR if not already** from `task/47-provision-postgres` → `master` summarizing provision work

---

## Self-Review

1. **Spec coverage:** PG-1…9 mapped to tasks; #48/#43/indexer excluded.  
2. **Clarity:** Exact table names, port, packages, SSH host.  
3. **Reversibility:** apt purge possible; config backups; Honcho untouched.  
4. **Minimalism:** No Docker; no ORM; smoke ≠ full indexer.
