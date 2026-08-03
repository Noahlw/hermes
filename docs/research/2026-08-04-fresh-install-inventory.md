# Fresh-install dependency & artifact inventory — Hermes reboot

> **Ticket:** [#79 — Fresh-install dependency & artifact inventory (reboot)](https://github.com/Noahlw/hermes/issues/79)
> **Parent map:** [#76 — Wayfinder: Hermes Reboot / Install repo as single entry point](https://github.com/Noahlw/hermes/issues/76)
> **Date:** 2026-08-04
> **Mode:** Investigation only — no code, no install scripts, no product decisions. Pointer-first; `BLOCKED` only where the repo evidence is genuinely missing.
> **Scope:** Every artifact in `Noahlw/hermes` relevant to installing/running Hermes. VM-side state is assumed deleted; only repo truth counts.

---

## 0. Headline

The **reboot-relevant** surface is narrow and mostly self-contained:
- Postgres + pgvector + age + rclone + psql are the only OS packages the repo installs/verifies directly (`scripts/vm/provision-hermes-postgres.sh`, `scripts/vm/provision-indexer.sh`, `db/migrate.sh`).
- Python is pinned only to `>=3.12` (`pyproject.toml`); `psycopg2-binary>=2.9` is the only runtime dependency (`pyproject.toml`).
- Honcho, Discord, Tailscale, the model API, the indexer systemd units, the gateway service, and the cron job runner are **described by the repo but not provisioned by it** — they live in `hermes-agent` (a separate upstream), in `~/.hermes/`, or in operator onboarding steps.
- The portable-restore chain (`key-bootstrap.sh` → `backup_postgres_drive.sh` → `restore_postgres_drive.sh` → `smoke-restore.sh`) is the only **end-to-end** install/restore workflow fully covered by the repo.

The **dead under reboot** surface — paths, commands, and runtime facts pinned to the deleted Oracle VM (`100.79.87.93`, `/home/ubuntu/.hermes/`) — is widespread in `docs/research/issue-39-discrepancy-ledger.md`, `docs/use-case-specification.md` §6, `hermes-v1-handoff.md`, `wayfinder-kickoff-prompt.md`, and `cron/jobs.json`. They describe what *was*; under reboot they cannot be assumed.

The **gap surface** is where a clean machine would stall: Tailscale auth, Discord bot token provisioning, model API key, gateway service unit, cron registration, profile/cron regeneration, and the `hermes-agent` install itself are not provided by any repo file.

---

## (a) Runtime dependency surface

Sources of truth cited inline; `[INFERENCE]` marks anything not pinned verbatim.

### a.1 Language runtime

| Dep | Pin | Where pinned |
|---|---|---|
| **Python** | `>=3.12` | `pyproject.toml:10` (`requires-python = ">=3.12"`) |
| **psycopg2-binary** | `>=2.9` (sole declared runtime dep) | `pyproject.toml:13` |
| **stdlib + dataclasses + pathlib** | n/a | used throughout `hermes/` (e.g. `hermes/profiles/config.py:9-13`, `hermes/honcho/isolation.py:11-13`, `hermes/personas/contract_gate.py:1-11`, `hermes/digest/formatter.py:7-11`) |

`pyproject.toml` only declares one runtime dep (`psycopg2-binary`); all other third-party libraries used elsewhere are stdlib or are imported *via* `psycopg2` inside guarded try-blocks (`hermes/indexer/db.py:9-15`).

### a.2 System packages the repo installs/verifies

| Package | Pin | Where pinned |
|---|---|---|
| **postgresql-16** | `dpkg -l postgresql-16` (apt) | `scripts/vm/provision-hermes-postgres.sh:40-47` |
| **postgresql-16-pgvector** | apt (best-effort, warns if missing) | `scripts/vm/provision-hermes-postgres.sh:49-53` |
| **postgresql-client-16** | required by `db/migrate.sh` (prints "install postgresql-client-16") | `db/migrate.sh:34-37`; also installed in `scripts/vm/provision-indexer.sh:12` (`postgresql-client-16`) |
| **psql** (postgresql-client-16) | binary check; missing → fail | `db/migrate.sh:34-37`, `scripts/vm/smoke-hermes-postgres.sh` usage, `scripts/vm/restore_postgres_drive.sh:95` |
| **pg_dump** | binary check; missing → fail | `scripts/vm/backup_postgres_drive.sh:123`, `scripts/vm/smoke-restore.sh:95` |
| **pg_restore** | binary check; missing → fail | `scripts/vm/restore_postgres_drive.sh:95`, `scripts/vm/smoke-restore.sh:96` |
| **age** (`age-keygen`, `age`) | binary check; missing → fail | `scripts/vm/key-bootstrap.sh:50`, `scripts/vm/encrypt-secrets.sh:57`, `scripts/vm/restore_postgres_drive.sh:94`, `scripts/vm/smoke-restore.sh:94` |
| **rclone** | binary check; remote must exist | `scripts/vm/key-bootstrap.sh:51-57`, `scripts/vm/encrypt-secrets.sh:58`, `scripts/vm/backup_postgres_drive.sh:124`, `scripts/vm/restore_postgres_drive.sh:96`, `scripts/vm/smoke-restore.sh:98` |
| **tar** | binary check | `scripts/vm/key-bootstrap.sh:52`, `scripts/vm/encrypt-secrets.sh:59` |
| **sudo** + `sudo -n` (non-interactive only) | required; rejects password prompts | `scripts/vm/provision-hermes-postgres.sh:33-34`, `scripts/vm/smoke-restore.sh` (sudo -u postgres for pg_restore at `:94-97, 167-172`) |
| **systemd (postgresql.service)** | cluster control via `systemctl` | `scripts/vm/provision-hermes-postgres.sh` restart/reload calls (around `:130-145`) |
| **git** | apt-installed by indexer provisioning | `scripts/vm/provision-indexer.sh:12` (`apt-get install -y -qq git python3 python3-pip python3-venv postgresql-client-16`) |
| **python3 / venv / pip** | apt-installed by indexer provisioning | `scripts/vm/provision-indexer.sh:12, 19-22` |
| **Ollama (local embedding/LLM host)** | not installed by repo; expected on `127.0.0.1:11434` | referenced in `cron/jobs.json:18` (`curl -s ... http://127.0.0.1:11434/api/tags`), `db/README.md:47`, `db/codebase_index/migrations/0001_init.sql:18` (`"source": "ollama"`), `docs/use-case-specification.md:266` |

> **[INFERENCE]** Ollama install path (e.g. `curl -fsSL https://ollama.com/install.sh | sh`) is **not** in the repo. Any installer must bring it from outside.

### a.3 Database schema pins (the only application-level pins)

| Pin | Where |
|---|---|
| **PG port = `127.0.0.1:5433`**, `listen_addresses = '127.0.0.1'`, `port = 5433` | `scripts/vm/provision-hermes-postgres.sh:15, 70-73` |
| **Two DBs on one Postgres instance**: `hermes`, `codebase_index` | `scripts/vm/provision-hermes-postgres.sh:16-19`, `db/README.md:5-8` |
| **Roles**: `hermes_app` (owns `hermes`), `codebase_index_app` (owns `codebase_index`) | `scripts/vm/provision-hermes-postgres.sh:17-19`, `db/README.md` |
| **`pg_hba` local trust for `127.0.0.1/32`** (idempotent, marker-gated insertion BEFORE the catch-all scram rule) | `scripts/vm/provision-hermes-postgres.sh:78-92` |
| **Honcho's Postgres stays on `:5432` (untouched)** | `scripts/vm/provision-hermes-postgres.sh:4-11`, `db/README.md:10`, `scripts/vm/backup_postgres_drive.sh:34-38`, `scripts/vm/restore_postgres_drive.sh:36-38` |
| **`vector` extension** on `codebase_index` | `db/codebase_index/migrations/0001_init.sql:4` |
| **Embedding default dim = 768** (`vector(768)`) | `db/codebase_index/migrations/0001_init.sql:17, 92-94`; smoke-checked at `scripts/vm/smoke-hermes-postgres.sh:142-143` |
| **Embedding default model = `nomic-embed-text`** | `db/codebase_index/migrations/0001_init.sql:18`; smoke-checked at `scripts/vm/smoke-hermes-postgres.sh:156-158` |
| **Two migration dirs under `db/`** — `hermes/migrations/*.sql`, `codebase_index/migrations/*.sql` | `db/migrate.sh:41-87`, `db/README.md:19-46` |
| **Hermes schema tables** (version 1 migration): `schema_migrations`, `audit_events`, `research_evidence`, `persona_task_scopes`, `session_briefs`, `digest_artifacts`, `digest_allowlists` | `db/hermes/migrations/0001_init.sql:8-99` |
| **Hermes digests table** (`digests`, ticket #62/#72) | `db/hermes/migrations/0002_digests.sql` |
| **Codebase index schema** (`repos`, `repo_refs`, `files`, `symbols`, `chunks` + generated `tsvector`, `chunk_embeddings`, `sync_cursors`, `schema_meta`) | `db/codebase_index/migrations/0001_init.sql:6-105` |
| **Migration runner is idempotent** — records each filename in `schema_migrations` per DB | `db/migrate.sh:59-72` |
| **Foreign key `(repo_id, ref_name)` on `repo_refs` and `sync_cursors`** | `db/codebase_index/migrations/0001_init.sql:36-42, 97-105` |

### a.4 Runtime services the repo *describes* (does not install)

These are pinned by **docs/cron/profile config**, not by install scripts. They survive the reboot as *intentional truth*, but the repo supplies neither install instructions nor service files.

| Service | Where | Pin |
|---|---|---|
| **Minimax (model API)** | `docs/use-case-specification.md`, `docs/adr/`, `CONTEXT.md` "MiniMax-only" | Provider name `MiniMax-M3`, model `MiniMax-M3`; no API key filename, no env-var pin in repo. `[INFERENCE]` env-var convention is the upstream `hermes-agent` model config. |
| **Discord (3 bots: Main Agent, Assistant, Tutor)** | `CONTEXT.md` "Discord persona bots"; `hermes/profiles/config.py:53-91`; `docs/specs/0001-deferred-persona-runtime-wiring.md:31-47` | Three Discord applications/bots, one per persona, one shared home channel (`DISCORD_HOME_CHANNEL`). Token env-vars: `DISCORD_BOT_TOKEN_MAIN_AGENT`, `DISCORD_BOT_TOKEN_ASSISTANT`, `DISCORD_BOT_TOKEN_TUTOR` (`hermes/profiles/config.py:61, 69, 77`). Allowlist env-var: `DISCORD_ALLOWED_USERS` (`hermes/profiles/config.py:147`). |
| **Tailscale** | `CONTEXT.md` "Tailscale-internal surface"; `docs/use-case-specification.md:288-304` (`D-EXP-1`); `hermes-v1-handoff.md:18` (non-negotiable) | Accepted Tailscale-internal listeners: SSH `22`, tailscaled `62773`, Hermes gateway `8642`, Open WebUI `3000`. No repo artifact installs Tailscale or auth-keys it. |
| **Honcho (working memory)** | `docs/research/memory-system-evaluation.md` "MEM-2 locked"; `CONTEXT.md` "Working memory"; `hermes/profiles/config.py:151-162` | Honcho Postgres on `127.0.0.1:5432` (separate from Hermes Postgres). Each persona gets a distinct `ai_peer` and `workspace_id` (`hermes_<persona_id>`). ADR 0004 marks backend `workspace_id` boundary as **unverified** — open gap. |
| **Local inference (Ollama)** | `db/codebase_index/migrations/0001_init.sql:17-19`, `cron/jobs.json:15-21`, `docs/use-case-specification.md:266` | Endpoint `http://127.0.0.1:11434`; embedding model `nomic-embed-text`. |
| **Hermes gateway service (`hermes-gateway.service`)** | `docs/use-case-specification.md:201`, `docs/adr/0004-hermes-agent-integration-model.md:7, 29`, `docs/runbooks/fresh-vm-restore.md:123-124, 161-164` | Lives on the VM; not supplied by this repo. The repo's contract-gate (`hermes/personas/`, `hermes/hermes_agent_plugin/`) is meant to plug in via hermes-agent's `pre_gateway_dispatch` hook (ADR 0004). No systemd unit file is shipped here. |
| **Indexer webhook service (`hermes-indexer-webhook.service`) + reconcile timer (`hermes-indexer-reconcile.timer`)** | `scripts/vm/provision-indexer.sh:59-100`, `docs/runbooks/fresh-vm-restore.md:126-129`, `docs/indexer-webhook-ops.md:91-114` | systemd units **are** generated by `scripts/vm/provision-indexer.sh` (best-effort — script falls back to a warning if the repo is not at `/home/ubuntu/hermes`). They pin `WorkingDirectory=/home/ubuntu/.hermes/indexer` and `INDEXER_CONFIG=/home/ubuntu/.hermes/indexer/config.json`. |
| **Cron runner** | `cron/jobs.json`, `docs/research/issue-39-discrepancy-ledger.md:142` (`CRON-4`) | Hermes cron is **in-process** (`InProcessCronScheduler`) driven by `cron/jobs.json`; there is **no system crontab and no systemd timers for Hermes cron jobs** (`issue-39-discrepancy-ledger.md:142`). `docs/runbooks/fresh-vm-restore.md:144-167` shows how to register, but the registration itself happens inside hermes-agent. |
| **rclone remote `gdrive:` pointing to Drive folder `17yovLP4BK1L_2jJKXbu4H4F-1kiGXzQM`** | `scripts/vm/key-bootstrap.sh:28-29`, `scripts/vm/encrypt-secrets.sh:27-29`, `scripts/vm/backup_postgres_drive.sh:41-42`, `scripts/vm/restore_postgres_drive.sh:40-41`, `scripts/vm/smoke-restore.sh:35-36` | Hard-coded Drive folder ID. Auth = whatever rclone OAuth flow produces locally; never written into repo. |
| **Repo path `/home/ubuntu/.hermes/`** | `scripts/vm/provision-hermes-postgres.sh:23`, `scripts/vm/key-bootstrap.sh:24`, `scripts/vm/provision-indexer.sh:5-7`, `cron/jobs.json:10, 26, 34, 45` | VM-specific. Reboot needs to redefine `HERMES_HOME` (every script honors an env override). |
| **Repo checkout path `/home/ubuntu/hermes`** | `scripts/vm/provision-indexer.sh:26-30`, `docs/runbooks/fresh-vm-restore.md:29-32` | Used as a literal default for `pip install -e /home/ubuntu/hermes`. Reboot needs to redefine this (the script warns "Install manually" if absent). |

### a.5 Remnants of the **out-of-V1** memory stack — listed here so the reboot does not rediscover them

| Remnant | Status | Source |
|---|---|---|
| **Qdrant** (standalone, Docker `qdrant_mem0`) | **MEM-7 uninstall** (2026-07-27, hybrid close) | `docs/use-case-specification.md:255`; `docs/research/memory-system-evaluation.md:73` "MEM-7 locked" |
| **mem0** | **MEM-7 uninstall**; replaced by Honcho for V1 working memory | `docs/use-case-specification.md:256`; `docs/research/memory-system-evaluation.md:73` |
| **AgentMemory (`iii`)** | **D-MEM-3 uninstall** (out of V1) | `docs/research/issue-39-discrepancy-ledger.md:130`; `docs/use-case-specification.md:251, 304` |
| **Neo4j** | **MEM-5 uninstall**; backups disabled in cron (`neo4j-drive-backup.enabled = false`) | `docs/use-case-specification.md:257`; `cron/jobs.json:43-48` (`"enabled": false`, note "Neo4j retired per MEM-5"); `docs/research/memory-system-evaluation.md:69` |
| **Telegram `gncsbot`** | **D-DISC-1 = A** removes Telegram from V1; legacy keys remain as facts only | `docs/research/issue-39-discrepancy-ledger.md:25, 153`; `CONTEXT.md` "Telegram as home channel" avoid-list |
| **SQLite `state.db` ~99 MB** | local-only working store of upstream hermes-agent, **not** an install truth | `docs/use-case-specification.md:241` |

No Qdrant / mem0 / agentmemory / neo4j dependency survives in any install-relevant script (`scripts/vm/`, `db/`, `pyproject.toml`, `hermes/`).

### a.6 `pyproject.toml` runtime install path

- Console script: `hermes-indexer = "hermes.indexer.__main__:main"` (`pyproject.toml:16-17`).
- Build backend: `setuptools>=64`, `setuptools.build_meta` (`pyproject.toml:1-3, 19-20`).
- `requires-python = ">=3.12"` (`pyproject.toml:10`).
- **Single declared runtime dep**: `psycopg2-binary>=2.9` (`pyproject.toml:13`).
- **No model SDK declared** — the package is purely policy + indexer + profile code. The actual LLM is wired through upstream hermes-agent's config, not this repo.

---

## (b) Artifact-by-artifact verdict

Legend:
- **Portable (survives the reboot)** = installs/rebuilds/runs without referring to the deleted VM.
- **VM-bound (dead under reboot)** = path/host/IP/secret references the deleted Oracle VM state.
- **Gap** = something the reboot needs that no repo artifact covers.

### b.1 Install/restore scripts (`scripts/vm/`)

| Artifact | Verdict | Why |
|---|---|---|
| `scripts/vm/provision-hermes-postgres.sh` | **Portable** (idempotent; env-overridable) | Self-installs PG 16 + pgvector, creates roles/DBs on `:5433`. Defaults to `127.0.0.1`, hard-coded PG version `16`, env-overridable port (`HERMES_PG_PORT`). Ubuntu/Debian `apt` only — confirmed by lines 21-23 (`/etc/postgresql/16/main`). |
| `scripts/vm/smoke-hermes-postgres.sh` | **Portable** | Probes schema/embedding dim/model against the migrated DBs. Reads from env vars (`HERMES_PGHOST`, etc.) — env-overridable. |
| `scripts/vm/provision-indexer.sh` | **Portable with VM-hardcoded path** | Installs git/python3 venv + creates systemd units. **Defaults**: `HERMES_HOME=/home/ubuntu/.hermes`, INDEXER_HOME=`$HERMES_HOME/indexer`, MIRRORS=`$HERMES_HOME/mirrors`. `pip install -e /home/ubuntu/hermes` is hard-coded as the indexer-source location; if absent the script logs a warning and points to `/path/to/hermes` (`scripts/vm/provision-indexer.sh:26-30`). |
| `scripts/vm/key-bootstrap.sh` | **Portable** (after Drive folder ID and `gdrive:` remote config) | Generates age identity, packages `.env` + `rclone.conf` into a tar, encrypts with `age -r $PUBLIC_KEY`, uploads to `gdrive:hermes-pg/secrets/secrets.age`. Hard-codes `DRIVE_FOLDER_ID=17yovLP4BK1L_2jJKXbu4H4F-1kiGXzQM` — operator-owned (env-overridable). |
| `scripts/vm/encrypt-secrets.sh` | **Portable** | Same chain as `key-bootstrap.sh`, but takes an existing identity file. |
| `scripts/vm/backup_postgres_drive.sh` | **Portable** | Dumps Hermes DB + codebase index DB + Honcho DB, prunes to retention N (`DAILY_RETENTION=14`, `WEEKLY_RETENTION=4`), uploads under `gdrive:hermes-pg/{daily,weekly}/<date>/`. |
| `scripts/vm/restore_postgres_drive.sh` | **Portable** | Downloads dumps + `secrets.age`, decrypts, `pg_restore --clean --if-exists` into live DBs. Supports `RESTORE_DATE`/`RESTORE_SOURCE=weekly`/`--dry-run`. |
| `scripts/vm/smoke-restore.sh` | **Portable** | Same chain into disposable DBs (`hermes_smoke`, `codebase_index_smoke`, `honcho_smoke`); does NOT touch production DBs. |

All eight `scripts/vm/` files are reboot-relevant (portable) **after** operator-supplied prerequisites are met: Tailscale auth on the VM, the `gdrive:` rclone remote already authed, and the age identity file obtained from secure storage.

### b.2 Database (`db/`)

| Artifact | Verdict | Why |
|---|---|---|
| `db/migrate.sh` | **Portable** | Reads `HERMES_PGHOST`/`HERMES_PGPORT`/`HERMES_PGUSER`/DB names from env with defaults (`127.0.0.1:5433`, `hermes`, `codebase_index`). Idempotent via `schema_migrations`. |
| `db/README.md` | **Portable** | Describes table purposes + connection defaults. |
| `db/hermes/migrations/0001_init.sql` | **Portable** | Pure SQL: schema_migrations, audit_events, research_evidence, persona_task_scopes, session_briefs, digest_artifacts, digest_allowlists. |
| `db/hermes/migrations/0002_digests.sql` | **Portable** | Adds `digests` table for the deferred ops-digest cron (Ticket #62/#72). |
| `db/codebase_index/migrations/0001_init.sql` | **Portable** | Creates `vector` extension + repos/repo_refs/files/symbols/chunks (with generated `tsvector` + GIN)/chunk_embeddings `vector(768)`/sync_cursors/schema_meta; seeds embedding dim=768 and model `nomic-embed-text`. |

### b.3 Python package (`pyproject.toml` + `hermes/`)

| Artifact | Verdict | Why |
|---|---|---|
| `pyproject.toml` | **Portable** | `requires-python = ">=3.12"`, `psycopg2-binary>=2.9`, console script `hermes-indexer`. |
| `hermes/indexer/` (config, db, mirror, parser, reconcile, sync, utils, webhook, `__main__`) | **Portable in code; bind time/config time depends on `IndexerConfig`** | All imports are stdlib + `psycopg2` (`hermes/indexer/db.py:9-15`). Defaults are hard-coded VM paths: `mirrors_root=/home/ubuntu/.hermes/mirrors` (`hermes/indexer/config.py:32`), webhook `port=8080`, default config path `/home/ubuntu/.hermes/indexer/config.json` (`hermes/indexer/config.py:113`). Each is env-overridable / JSON-overridable. |
| `hermes/personas/` (contract_gate, adapters, contracts/*.json) | **Portable** | Pure-Python policy; tests cover all 5 contracts and gate decisions (`tests/test_persona_contract_gate.py`, `tests/test_persona_adapters.py`). |
| `hermes/hermes_agent_plugin/` (dispatch.py, confirm_delete.py) | **Portable** (with declared-but-deferred wire-up) | Self-contained plugin-package to be registered with hermes-agent's `pre_gateway_dispatch` hook; ADR 0004 notes the plugin is **not yet** wired up on the live VM (open follow-up). |
| `hermes/honcho/` (isolation.py) | **Portable** | Pure check; reads `honcho.json` content per profile. ADR 0004 marks Honcho `workspace_id`-per-profile as **unverified**. |
| `hermes/profiles/` (config.py, provision.py) | **Portable** | Defines the 5 V1 profiles, generates `config.yaml` / `.env` / `honcho.json` / `cron/jobs.json` per profile (`hermes/profiles/config.py:94-195`); `.env` file has placeholders for `DISCORD_BOT_TOKEN_*` and `DISCORD_ALLOWED_USERS` (`hermes/profiles/config.py:140-148`). |
| `hermes/digest/` (formatter.py) | **Portable** | Pure stdlib; produces the per-job status digest text. |
| `hermes/__init__.py` (empty) | **Portable** | n/a |
| `hermes/README.md` | **(does not exist)** — no markdown README in `hermes/` (verified). Top-level `README.md` is referenced by `pyproject.toml:9` but the file does not exist in the repo today. | **GAP** (see (c)) |

### b.4 Docs

| Artifact | Verdict | Why |
|---|---|---|
| `CONTEXT.md` (glossary) | **Portable** (semantic intent) | Defines domain terms; binds contracts. Doesn't pin versions but pins contracts. |
| `docs/runbooks/fresh-vm-restore.md` | **Mostly portable**, with VM-bound command paths | Documents the install/restore flow (clone → provision PG → restore DBs → smoke → source `.env` → restart services → re-fetch repos → register cron). Pull-quotes assume `/home/ubuntu/hermes` checkout (`docs/runbooks/fresh-vm-restore.md:29-32`) and `~/.hermes/` runtime (`docs/runbooks/fresh-vm-restore.md:111, 117`). Restoration *itself* is portable. |
| `docs/adr/0001-coding-agent-mcp-information-suite.md` | **Portable (decision)** | Six named MCP tools, no install truth. |
| `docs/adr/0002-mcp-invocation-contracts.md` | **Portable** (decision) | Tool invocation contracts (deferred to #49 per ADR 0001). |
| `docs/adr/0003-v1-persona-roster-and-contracts.md` | **Portable** (decision) | Locks the 5-persona roster + 3-bots Discord model. |
| `docs/adr/0004-hermes-agent-integration-model.md` | **Portable** (decision + open gap) | Locks `pre_gateway_dispatch` integration seam and 5-profile model. Explicitly flags Honcho `workspace_id`-per-profile as **unverified**. |
| `docs/specs/0001-deferred-persona-runtime-wiring.md` | **Portable (design captured, not built)** | Bot wiring / native confirm button / cron digest / Honcho workspace isolation. None of these are installed; they're design captures for follow-up tickets. |
| `docs/use-case-specification.md` | **Mixed** | §1-§5, §8 = V1 target (portable). §6 = observed VM facts (`CONFIRMED` facts on the deleted VM are dead under reboot). §6.7 explicit `weekly-workspace-cleanup 401` debt is carried as **`DEBT`**. |
| `docs/research/postgres-provisioning-47.md` | **Portable** (locked PG-* decisions) | PG-1…PG-9. The baseline table mentions `live since 2026-07-27T05:36Z` (a VM fact); under reboot it is meta, not install truth. |
| `docs/research/memory-system-evaluation.md` | **Portable (decisions)** | MEM-1…MEM-8 lock the **out-of-V1** removes. `MEM-1` references Qdrant contextually — locked **decision**, not a new install truth. |
| `docs/research/codebase-indexing-strategy.md` | **Portable (decisions)** | IDX-1…IDX-7 architecture decisions. Locks "hosted embeddings allowed" (dedicated narrowing of the no-public-exposure non-negotiable). |
| `docs/research/issue-39-discrepancy-ledger.md` | **Mostly VM-bound** | Audit of live VM facts vs spec; under reboot, every row is historical. `D-NN-1` through `D-MEM-3` decisions carry forward as portable **decisions**; the live-verify evidence timestamps are not. |
| `docs/indexer-webhook-ops.md` | **Portable** (operations doc) | The webhook handler ships inside `hermes/indexer/webhook.py`. Public exposure is via Tailscale Funnel (`docs/indexer-webhook-ops.md:122-126`). Repo supplies no nginx/caddy config. |

### b.5 Cron

| Artifact | Verdict | Why |
|---|---|---|
| `cron/jobs.json` (4 active jobs, 1 disabled) | **Portable in JSON intent** — but the **commands they invoke are VM-bound** | The 5 listed cron jobs reference `/home/ubuntu/.hermes/scripts/*` paths; only `portable-postgres-backup` (calls `scripts/vm/backup_postgres_drive.sh`) maps to a script in this repo. `vm_health.sh`, `weekly-cleanup.sh`, and `backup_neo4j.sh` are **not** in this repo — they're VM-local. Under reboot, the JSON template survives as a starting point; the operator must regenerate the path. |

### b.6 Tests (`tests/`) — what they pin

| Test | Pins | File |
|---|---|---|
| `test_cron_jobs.py` | The 5 expected cron job IDs (`vm-health-check`, `ollama-keep-alive`, `weekly-workspace-cleanup`, `portable-postgres-backup`, `neo4j-drive-backup` with `enabled: false`) | `tests/test_cron_jobs.py:23-28` |
| `test_indexer_config.py` | Default excluded-paths and validation logic for `IndexerConfig` | `tests/test_indexer_config.py` |
| `test_profiles.py` | Roster of 5 personas, Discord-vs-MCP split, the `0 7 * * *` ops-digest schedule 1 hour after `vm-health-check` at `0 6 * * *` | `tests/test_profiles.py:27-30, 180-186` |
| `test_honcho_isolation.py` | Each profile's `ai_peer` and `workspace_id` are distinct across all 5 personas | `tests/test_honcho_isolation.py` |
| `test_persona_adapters.py` / `test_persona_contract_gate.py` | Gate decision enum + contracts JSON validation | `tests/test_persona_*.py` |
| `test_hermes_agent_plugin.py` | Plugin `pre_gateway_dispatch` hook registration and Discord dispatch routing | `tests/test_hermes_agent_plugin.py` |
| `test_indexer_sync.py` / `test_indexer_parser.py` / `test_indexer_webhook.py` | Sync, parser, webhook behaviors (mocked) | `tests/test_indexer_*.py` |
| `test_digest.py` | Digest formatter per-job statuses (uses `ollama-keep-alive` as fixture) | `tests/test_digest.py` |
| `test_confirm_delete.py` | Confirm-delete UX wiring via Discord interactions | `tests/test_confirm_delete.py` |

All tests are stdlib `unittest` — no pytest, no third-party deps (`tests/test_indexer_config.py:9-14` etc.).

Tests pin **policy contracts**, not state; they remain valid across reboot if the deps (`hermes/` package + psycopg2) are still satisfied.

### b.7 Top-level files

| Artifact | Verdict | Why |
|---|---|---|
| `pyproject.toml` | **Portable** | See (a.6). |
| `.gitignore` | **Portable** | Excludes `__pycache__`, `*.pyc`, `.scratch/`. |
| `hermes-v1-handoff.md` | **VM-bound** | Describes the **deleted** VM (`Hermes Agent v0.15.1 via Docker Compose`, `Triple-stack memory`, `Tailscale up (VM: 100.79.87.93, Mac: 100.104.102.94)`). Carries forward the non-negotiables, not the facts. |
| `wayfinder-kickoff-prompt.md` | **VM-bound** | "What's on the VM already" section is fully dead under reboot. Non-negotiables and tickets list carry forward. |
| No top-level `README.md` (only `pyproject.toml:9` references one) | **GAP** | (see (c)) |

---

## (c) Gaps — what a clean machine needs that no repo artifact covers

> **Hard gap row**: anything on this list, if missing at first boot, breaks a documented installer or non-negotiable.

1. **`hermes-agent` runtime itself.** Every script and ADR assumes a working `hermes-agent` venv + `hermes-gateway.service` on the VM (`docs/use-case-specification.md:201`, `ADR 0004`, `cron/jobs.json` InProcessCronScheduler). The repo does **not** install hermes-agent; it ships only the policy, profile, and indexer code that *plugs into* it.

2. **`hermes-gateway.service` systemd unit.** Referenced in `docs/use-case-specification.md:201` and `docs/runbooks/fresh-vm-restore.md:123-124, 161-164`; not authored in any repo file (verified — only `hermes-indexer-webhook.service` and `hermes-indexer-reconcile.{service,timer}` are templated in `scripts/vm/provision-indexer.sh:59-100`).

3. **Tailscale installation + auth-key registration on the VM.** Tailscale is a non-negotiable (`hermes-v1-handoff.md:18`); the repo contains `tailscale funnel 8080` as doc-only advice (`docs/indexer-webhook-ops.md:122-126`). Nothing in the repo installs Tailscale, invokes `tailscale up`, or fetches a pre-auth key.

4. **Drive folder ownership.** All scripts hard-code `DRIVE_FOLDER_ID=17yovLP4BK1L_2jJKXbu4H4F-1kiGXzQM`. A clean reboot that lacks access to that same Drive folder cannot restore anything. The folder itself is operator-owned.

5. **rclone OAuth/credential setup against the `gdrive:` remote.** Scripts `fail` if `rclone lsd gdrive:` cannot reach the folder (`scripts/vm/key-bootstrap.sh:55-57`). The repo never runs `rclone config`.

6. **`.env` shape, secret values, and key naming.** The provisioning scripts depend on `${HERMES_HOME}/.env` existing (`scripts/vm/key-bootstrap.sh:23-24`, `scripts/vm/encrypt-secrets.sh:22-23`); the only `.env` template the repo provides is the per-profile placeholder (`hermes/profiles/config.py:140-148`) with `PLACEHOLDER_DISCORD_BOT_TOKEN` / `PLACEHOLDER_COMMA_SEPARATED_USER_IDS`. The full `.env` key list (which tokens, which env-var names beyond `DISCORD_BOT_TOKEN_*`) is **not** documented in any repo file.

7. **Three real Discord bot tokens + an allowlist of Discord user IDs.** `CONTEXT.md` "Discord persona bots" says "one Discord application/bot per Discord-reachable persona"; `hermes/profiles/config.py` lists the three token env-vars; `docs/specs/0001-deferred-persona-runtime-wiring.md:92` calls out "three real Discord bot tokens must be created in the Discord developer portal and the operator must be on hand to authorize them on the home guild/channel." No repo file generates or registers these.

8. **Model API key (`MiniMax-M3`).** Pinned by `CONTEXT.md` "MiniMax-only" provider rule; the env-var name/key naming is **not** in this repo. Provider configuration lives in upstream hermes-agent.

9. **Honcho itself (working memory).** `CONTEXT.md` "Working memory (V1)" + `MEM-2 locked` require Honcho as the working-memory store. The repo pins Honcho Postgres on `127.0.0.1:5432` (used by `backup_postgres_drive.sh:35-38` and `restore_postgres_drive.sh:35-38`), but **does not install Honcho, its compose file, or its `ai_peer`/`workspace_id` config** beyond the per-profile `honcho.json` template (`hermes/profiles/config.py:151-162`).

10. **Webhook-public exposure.** `docs/indexer-webhook-ops.md:115-126` recommends Tailscale Funnel or a reverse proxy for port `8080`; no nginx/caddy config ships in the repo.

11. **Five `hermes-agent` profiles on disk.** `hermes/profiles/provision.py` produces a `ProvisionPlan` (idempotent manifest), but no script *applies* it to a target VM. `docs/runbooks/fresh-vm-restore.md` expects the operator to "Restart Hermes services" as a black box (`docs/runbooks/fresh-vm-restore.md:120-129`); the actual `plan_provision` write-out is not wired.

12. **Cron registration on a fresh VM.** `docs/runbooks/fresh-vm-restore.md:144-167` shows how to add the `portable-postgres-backup` job. But under reboot, **all five** jobs in `cron/jobs.json` reference scripts that don't exist on disk (`/home/ubuntu/.hermes/scripts/{vm_health.sh, weekly-cleanup.sh, backup_neo4j.sh}`); only the `portable-postgres-backup` invocation maps to a repo file. Three of the five jobs (`vm-health-check`, `ollama-keep-alive`, `weekly-workspace-cleanup`) reference VM-private scripts that the reboot must author or import.

13. **`/home/ubuntu/hermes` checkout path.** `scripts/vm/provision-indexer.sh:26-30` falls back to a `WARNING` if `/home/ubuntu/hermes` is missing — the entire `pip install -e` flow becomes a manual step. There is no helper to clone + checkout + editable install.

14. **Top-level `README.md`.** `pyproject.toml:9` (`readme = "README.md"`) implies a top-level README; no such file exists in the tree. There is no `hermes/README.md` either (verified empty in `ls -la hermes/`). Anyone discovering the repo on GitHub gets no install guidance.

15. **Ollama installation + `nomic-embed-text` model pull.** `db/README.md:47`, `cron/jobs.json:18`, `db/codebase_index/migrations/0001_init.sql:18`, and the smoke checks (`scripts/vm/smoke-hermes-postgres.sh:127-143, 156-158`) all assume Ollama on `127.0.0.1:11434` with `nomic-embed-text` and dim 768. The repo installs none of this.

16. **`hermes-agent` 5-profile gateway multiplex wiring.** Per `docs/specs/0001-deferred-persona-runtime-wiring.md:33-37`, the three Discord profiles get multiplex `gateway.multiplex_profiles: true` in the primary profile; the repo's `generate_config_yaml` (`hermes/profiles/config.py:94-126`) writes that key, but the primary profile's `config.yaml` is not actually written anywhere (only the per-profile configs).

---

## (d) What backup/restore implies about the intended fresh-install flow

The backup/restore scripts in `scripts/vm/` plus the runbook in `docs/runbooks/fresh-vm-restore.md` together describe the canonical fresh-install path the repo actually supports. They imply an **ordered, three-tier truth model**:

### d.1 Three tiers of "install truth"

1. **Git = the only authoritative code/config for the new machine** (`docs/runbooks/fresh-vm-restore.md:13-15`). Code, schema, profiles, cron template, scripts all come from the GitHub clone.
2. **Drive = authoritative durable state** (Postgres dumps + encrypted secrets). The folder `17yovLP4BK1L_2jJKXbu4H4F-1kiGXzQM` and `gdrive:hermes-pg/{daily,weekly,<date>/` is the only durable record of Hermes DB, codebase index DB, and Honcho Postgres.
3. **Operator = unique holder of the age unlock key** (`docs/runbooks/fresh-vm-restore.md:16`; `CONTEXT.md` "Unlock key file"). The age private key is **never** on Drive, **never** in git, **never** auto-regenerated; losing it is total data loss for any encrypted archive on Drive.

### d.2 Ordering the scripts prescribe

Reading the scripts head-to-tail, plus the runbook, implies this **fresh-install ordering** (without committing to a product design):

1. **Bootstrap age key once** (`scripts/vm/key-bootstrap.sh`) — generate the identity, package a minimal `.env` + `rclone.conf`, encrypt to `secrets.age`, upload to `gdrive:hermes-pg/secrets/secrets.age`. The operator saves the identity file offline. After bootstrap, `scripts/vm/encrypt-secrets.sh` re-encrypts on secret rotation.
2. **Install backup agent** (`scripts/vm/backup_postgres_drive.sh` registered in `cron/jobs.json`) so future VMs also produce durable dumps. `cron/jobs.json` lists it at `0 5 * * *` with `--weekly` and a `DAILY_RETENTION=14 / WEEKLY_RETENTION=4` retention policy.
3. **Install Postgres (Hermes dedicated instance)** (`scripts/vm/provision-hermes-postgres.sh`) — apt-managed PostgreSQL `16` + `pgvector` on `127.0.0.1:5433` with two DBs and two app roles. Idempotent on every run.
4. **Apply schema** (`db/migrate.sh all`) — `schema_migrations` recorded per DB; idempotent.
5. **Restore from Drive** (`scripts/vm/restore_postgres_drive.sh <identity>`) — finds the latest daily backup by default; supports a specific `RESTORE_DATE` or `RESTORE_SOURCE=weekly`. Disposes of the `--dry-run` flag for verification.
6. **Smoke the restore** (`scripts/vm/smoke-restore.sh <identity>`) — pg_restore into *disposable* DBs (`hermes_smoke`, `codebase_index_smoke`, `honcho_smoke`); does not touch production.
7. **Verify live Postgres** (`scripts/vm/smoke-hermes-postgres.sh`) — confirms both DBs accept inserts (audit_events, research_evidence, digest_allowlists), FTS works (chunks + to_tsquery), pgvector dim=768 and model=`nomic-embed-text`, Honcho :5432 still listening.
8. **Source `.env` (decrypted from the archive), install rclone.conf** (`docs/runbooks/fresh-vm-restore.md:100-118`).
9. **Register the indexer systemd units** (`scripts/vm/provision-indexer.sh:59-100`) so `hermes-indexer-webhook.service` and `hermes-indexer-reconcile.timer` exist; run `python -m hermes.indexer first-index owner/repo` per allowed repository.
10. **Bring up gateway + cron** (`docs/runbooks/fresh-vm-restore.md:120-167`) — restart `hermes-gateway.service` (which the repo does **not** author), then register/edit `cron/jobs.json` to wire the cron template. The `portable-postgres-backup` cron is the only one whose `command` path resolves into this repo.

The implications the **scripts themselves** carry (regardless of any operator workflow outside the repo):

- **Idempotency is a hard requirement**: every script (`provision-hermes-postgres.sh`, `key-bootstrap.sh`, `migrate.sh`, the indexer provisioner, `backup_postgres_drive.sh`, `restore_postgres_drive.sh`) is safe to re-run on a partially-set-up machine. Several explicitly re-check existence gates (`scripts/vm/provision-hermes-postgres.sh:89-92` marker-gated `pg_hba.conf` insertion).
- **The age key is symmetric to losing the database**: `scripts/vm/restore_postgres_drive.sh:141-144` will *fail hard* if the identity cannot decrypt; the operator never has a path to recover plaintext without the key.
- **Restore order is Hermes DB → codebase index DB → Honcho DB** (`scripts/vm/restore_postgres_drive.sh:170-189`); each gets `--clean --if-exists`. The smoke variant uses disposable `*_smoke` databases.
- **Backups must include `secrets.age`** (encrypted only) — Drive contents are `gdrive:hermes-pg/{daily,weekly,<date>}/<dump>.dump` plus `gdrive:hermes-pg/secrets/secrets.age`. Drives **should not** contain plaintext `.env`, `rclone.conf`, or any age private key (`CONTEXT.md` "Unlock key file" avoid-list).
- **The cron runner is not system cron**: `cron/jobs.json:1-3` says "Managed by hermes-agent InProcessCronScheduler". Restoring cron means registering entries in hermes-agent — not adding a system crontab line.
- **The `portable-postgres-backup` job** at `0 5 * * *` with `--weekly` (`cron/jobs.json:30-39`) is the only cron entry whose command path resolves inside this repo; the others (`vm-health-check`, `ollama-keep-alive`, `weekly-workspace-cleanup`) invoke VM-local scripts that the reboot must reconstruct.

---

## (e) First-draft fresh-install checklist

> Designed for grilling tickets to react to. Mark each item ✅ / ❓ / ❌ when a ticket owns it. No scripts/commit implied.

### Tier 0 — Operator-provided prerequisites (no repo install needed)

- [ ] **Tailscale installed** on the target VM, the same Tailscale tailnet/account reachable; auth-key (or interactive `tailscale up`) supplied.
- [ ] **Tailscale Funnel** configured for `http://127.0.0.1:8080` *only if* the GitHub-webhook indexer is enabled (otherwise the Tailscale-internal port list per `D-EXP-1`: SSH `22`, tailscaled `62773`, Hermes gateway `8642`, Open WebUI `3000`).
- [ ] **Drive folder access**. Same Google account, same folder (`17yovLP4BK1L_2jJKXbu4H4F-1kiGXzQM`); the operator holds the matching `rclone.conf`.
- [ ] **age identity file** for the operator's Hermes-as-a-service identity. Retrieved from secure storage; never shared, never uploaded.
- [ ] **Three Discord bot tokens** (`DISCORD_BOT_TOKEN_MAIN_AGENT`, `DISCORD_BOT_TOKEN_ASSISTANT`, `DISCORD_BOT_TOKEN_TUTOR`) + the allowlist (`DISCORD_ALLOWED_USERS`) + `DISCORD_HOME_CHANNEL`.
- [ ] **Model API key + Hermes-agent provider config** for `MiniMax-M3`.

### Tier 1 — Repo-driven install (scripted)

- [ ] **Clone** `https://github.com/Noahlw/hermes.git` to a known path (e.g. `~/.hermes/hermes-repo` or `/opt/hermes`).
- [ ] `pip install -e .` from the repo root (`pyproject.toml` pins `psycopg2-binary>=2.9`).
- [ ] `sudo ./scripts/vm/provision-hermes-postgres.sh` — idempotent; installs `postgresql-16` + `postgresql-16-pgvector`, creates `hermes_app` / `codebase_index_app` roles, `hermes` / `codebase_index` DBs on `127.0.0.1:5433`.
- [ ] `bash db/migrate.sh all` — applies `db/hermes/migrations/000{1,2}*.sql` and `db/codebase_index/migrations/0001_init.sql`.
- [ ] `./scripts/vm/smoke-hermes-postgres.sh` — must end `ALL_PASS`; proves dim=768, model=`nomic-embed-text`, Honcho :5432 still up.

### Tier 2 — Restore durable state (Drive + key)

- [ ] (Skip if fresh repo, no data to restore.) `./scripts/vm/restore_postgres_drive.sh <identity>` — or `--dry-run` first; or `RESTORE_DATE=YYYY-MM-DD`.
- [ ] (Verify integrity first.) `./scripts/vm/smoke-restore.sh <identity>` — must succeed with summary `OK` before production restore.
- [ ] Place decrypted `~/.hermes/.env` and `~/.config/rclone/rclone.conf` where expected (`docs/runbooks/fresh-vm-restore.md:108-118`).

### Tier 3 — Indexer + first sync

- [ ] `./scripts/vm/provision-indexer.sh` — installs git/python3 venv, writes `indexer/config.json`, writes `hermes-indexer-webhook.service` + `.timer`.
- [ ] Write a real `indexer/config.json` (the script writes a default that's empty allowlist).
- [ ] `python -m hermes.indexer first-index owner/repo` per allowlisted repo.

### Tier 4 — Services + cron (NOT repo-scripted)

- [ ] **Install hermes-agent + `hermes-gateway.service`** (out of repo). Bring up the gateway.
- [ ] **Wire profile provisioning** (5 profiles) by running `hermes.profiles.provision.plan_provision(...).apply()` against the operator `HERMES_HOME` — **write plan, no apply helper in repo**.
- [ ] **Run `provision.py` followed by writing `config.yaml` + `.env` for each profile** using `hermes.profiles.config.generate_*` helpers; copy/symlink so the gateway finds them.
- [ ] **Register cron template**: copy `cron/jobs.json` into `$HERMES_HOME/cron/jobs.json`, fix command paths to absolute paths that resolve on the new VM (e.g. `/opt/hermes/scripts/vm/backup_postgres_drive.sh` for `portable-postgres-backup`); restart hermes-gateway to pick up.
- [ ] **Re-create the three VM-local cron scripts** (`vm_health.sh`, `weekly-cleanup.sh`) — they are referenced by `cron/jobs.json` but are **not** in this repo. Until they exist, those three jobs will be broken.
- [ ] **Honcho**: install + bring up Honcho compose on `:5432` (separate from Hermes Postgres `:5433`); confirm Honcho API reachable.

### Tier 5 — Models + embedding host

- [ ] **Install Ollama** + pull `nomic-embed-text` (and any other models the deployment uses); keep on `127.0.0.1:11434`.
- [ ] Confirm `cron/jobs.json` `ollama-keep-alive` hits `200`.

### Tier 6 — Verify + ticket-acceptance

- [ ] `library_search` smoke (manual or scripted) returns expected hits on the restored index.
- [ ] Each Discord bot id responds to an @-mention on the home channel.
- [ ] `run_ops_digest` writes to `digests` on Hermes DB (`db/hermes/migrations/0002_digests.sql` table) once Ticket #62 implementation lands; until then skip.
- [ ] Backup cron (`portable-postgres-backup`) produces a new dated directory under `gdrive:hermes-pg/daily/` within 24 h.

---

## Status

**Status: READY** — every dependency and artifact claim in this report is cited to a file path in the repo. The eight `scripts/vm/` artifacts, `db/`, `pyproject.toml`, the `hermes/` package, the ADRs/specs, the runbook, the cron template, and the test suite are fully inventoried.

**Report path:** [`docs/research/2026-08-04-fresh-install-inventory.md`](2026-08-04-fresh-install-inventory.md).

### Key findings (≤10)

- **Dependency surface is tiny.** `psycopg2-binary>=2.9` and `python>=3.12` are the only PyPI pins (`pyproject.toml`); apt installs are `postgresql-16` + `postgresql-16-pgvector` + `postgresql-client-16` + `git` + `python3(-venv/-pip)` (`scripts/vm/provision-*.sh`). Three CLI tools (`age`, `rclone`, `tar`) and one service (`postgresql` via systemd) are the rest.
- **Honcho, Discord, Tailscale, MiniMax are described but not installed.** The repo tells you *what* must exist and *what* it does; the install path for any of those is outside this repo.
- **Hermes Postgres + the codebase index DB + Honcho Postgres = three DBs on two ports** (`:5433` for Hermes × 2 logical DBs, `:5432` Honcho only). The two `:5433` DBs are pinned here (`scripts/vm/provision-hermes-postgres.sh:5-19`); Honcho's `:5432` and its `ai_peer`/`workspace_id` per-profile isolation is partially templated (`hermes/profiles/config.py:151-162`) and partially **unverified** (ADR 0004).
- **Embeddings are pinned to `vector(768)` and Ollama `nomic-embed-text`** in the schema (`db/codebase_index/migrations/0001_init.sql:17-19`) and asserted in the smoke (`scripts/vm/smoke-hermes-postgres.sh:127-158`). Ollama itself is not installed by the repo — it's a deployed VM fact.
- **The portable-restore chain is the only fully repo-scripted end-to-end install path**: `key-bootstrap.sh` → `encrypt-secrets.sh` (rotation) → `backup_postgres_drive.sh` → `restore_postgres_drive.sh` → `smoke-restore.sh`. The age private key is *by-design* the operator's responsibility and the single point of loss.
- **Qdrant / mem0 / agentmemory / neo4j / Telegram are all out-of-V1 leftovers.** Cron's `neo4j-drive-backup` is already `enabled: false` in the template (`cron/jobs.json:43-48`); the other three are explicit uninstalls per `docs/research/memory-system-evaluation.md` "MEM-5/MEM-7 locked" and `docs/research/issue-39-discrepancy-ledger.md:130, 153`.
- **Survives the reboot (portable)**: all 8 `scripts/vm/*.sh`, all of `db/`, `pyproject.toml`, `hermes/`, `cron/jobs.json` (as JSON template), `docs/runbooks/fresh-vm-restore.md`, `docs/adr/*`, the four ADRs/specs, `docs/indexer-webhook-ops.md`, the research notes as **decisions**.
- **Dead under reboot (VM-bound)**: `hermes-v1-handoff.md` "Current VM state", `wayfinder-kickoff-prompt.md` "What's on the VM already", `docs/use-case-specification.md` §6 observations, every path under `/home/ubuntu/.hermes/` and `/home/ubuntu/hermes/` in scripts' defaults, the `cron/jobs.json` commands that call `vm_health.sh` / `weekly-cleanup.sh` / `backup_neo4j.sh` (none of those scripts are in this repo).
- **Top three gaps**: (a) `hermes-agent` itself + `hermes-gateway.service` unit — the gateway is the runtime and is not in this repo; (b) Tailscale auth + Discord bot tokens + MiniMax key — all operator prerequisites, none generated by the repo; (c) the 5 `hermes-agent` profiles — `hermes/profiles/provision.py` *plans* them but the apply/launch step is unowned; same for cron registration, Ollama install, and webhook-public exposure.
- **Test surface is heavy and portable**: 13 `tests/test_*.py` files pin policy contracts (roster of 5 personas, cron job IDs, Honcho isolation, confirm-delete UX, indexer parse/sync/webhook, digest formatter) — none require a live VM except via mocks.
- **First-draft checklist (Tier 0–6 above)** explicitly notes which items are operator-only vs scriptable; the four `BLOCKED`-style items in §(c) gaps 11/12/13/14 (profile apply, cron registration on fresh VM, `pip install` path fallback, missing top-level README) are the cleanest candidates for the next round of grilling tickets.
