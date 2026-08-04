---
status: accepted
---

# Hermes reboot install contract: hybrid bootstrap + runbook, zero-data fresh install, full-stack acceptance without Ollama

The Hermes repo is being reworked into the single install/setup entry point (map #76). The prior VM and all setup are deleted; this is a zero-data start. This ADR records the install contract settled by grilling ticket #80, grounded in the fresh-install inventory research (#79, `docs/research/2026-08-04-fresh-install-inventory.md`).

Key facts from #79: the repo already scripts the deterministic 80% of provisioning (`scripts/vm/provision-hermes-postgres.sh`, `provision-indexer.sh`, the backup/restore chain), while the runtime itself (`hermes-agent` + `hermes-gateway.service`), secrets shape, profile apply, and cron registration have **no repo artifact** — they are the unscripted tail.

## Decision

1. **Mechanism — hybrid.** A thin `setup/install.sh` chains the existing deterministic scripts in order (DB provision → smoke gate → indexer → restore-if-backup → final smoke), and a top-level `INSTALL.md` runbook carries the unscripted operator/agent steps (Tailscale up, `.env` creation, gateway bring-up, profile apply, cron registration). A coding agent runs the script, then follows the runbook for the tail. Docker Compose is rejected: it contradicts the settled systemd/apt direction (ADRs 0003/0004, `CONTEXT.md`: Hermes database).
2. **Redo semantics — fresh-install-only + phase smoke gates.** Redo = re-clone/re-run from the top; the bootstrap halts on the first failing smoke (`smoke-hermes-postgres.sh` etc.). No **new** idempotency machinery is built: the existing provision scripts are already idempotent by design (`provision-hermes-postgres.sh` header: “Idempotent on every run” — dpkg gates around apt installs, marker-guarded pg_hba edits, role/DB existence checks), so re-running the scripted phases from the top is safe. **Caveat:** redo semantics assume a disposable target; revisit if #78 lands on a non-disposable target (e.g. local Mac).
3. **Secrets — template-driven, zero-data start.** The Drive backup was never built, so there is nothing to restore. Happy path: committed `.env.example` → installer copies to `.env`, validates every required key, fails fast listing exactly what is missing. The age-key/Drive backup-restore chain (`key-bootstrap.sh` → `encrypt-secrets.sh` → `backup_postgres_drive.sh` → `restore_postgres_drive.sh` → `smoke-restore.sh`) is retained as **scripted DR only** and is **unverified** — it has never executed end-to-end; prototype #77 must dry-run it before it can be trusted.
4. **Install acceptance — full stack, minus Ollama.** "Working Hermes" = all of: `smoke-hermes-postgres.sh` passes (Hermes DB + codebase-index DB on `:5433`, pgvector); gateway service up and systemd-enabled; all three Discord bots (Assistant, Tutor, Main Agent) answer an @-mention on the home channel; cron jobs registered; indexer completes a first sync; `library_search` returns the MCP envelope (`ok: true`); `.env` validation clean. **Ollama is not installed:** the target is Oracle Cloud free tier (2 CPU / 12 GB RAM), which cannot serve it. The embedding provider is therefore an open product decision (feeds #43/#38); the schema's `vector(768)`/`nomic-embed-text` pins and the `ollama-keep-alive` cron entry are suspended pending that decision.

## Considered options

- Pure runbook (rejected: agent re-derives ordering/state; the scriptable 80% goes unscripted)
- Pure bootstrap script (rejected: secrets, Discord auth, and profile apply cannot be scripted well today)
- Hybrid — thin bootstrap + runbook (chosen)
- Docker Compose (rejected: contradicts settled systemd/apt architecture)

## Consequences

- Install artifacts land in `setup/` plus top-level `INSTALL.md`, executed by restructure ticket #81.
- The #79 gap list (gateway + service unit not in repo; 5-profile apply unowned; cron registration; `.env` shape) defines the runbook tail.
- Prototype #77 is the first executor of this contract and the verifier of the unverified DR chain.
- Anything in the acceptance that requires Ollama or `nomic-embed-text` locally is invalid until the embedding-provider decision lands.
- If #78 chooses a non-disposable target, decision 2 (redo semantics) is revisited.

## Prototype correction (#77, 2026-08-04)

First execution of this contract on a fresh Ubuntu 24.04 aarch64 VM found the
recorded chain unimplementable as written:

- **Migrations were never applied by the chain.** `provision-hermes-postgres.sh`
  creates roles/databases only, and `provision-indexer.sh`'s own `db/migrate.sh
  codebase_index` call runs as `$USER` (no DDL rights on the owner-role DBs) and
  soft-fails with `|| echo`. `install.sh` now applies `db/migrate.sh` as the
  DB-owner roles (`hermes_app` / `codebase_index_app`) after provisioning, with a
  one-time superuser `CREATE EXTENSION vector` (peer-auth unix socket) first.
- **Smoke gate ran before the indexer provision.** Checks `f`–`l` target
  `codebase_index` tables that only phase 4 created; the gate now runs after the
  indexer provision. (In the original run, the cascade `FAIL:cdefghijkl` traced
  to the missing schema — checks `g`/`h` showed `VALUES (, …)` from empty
  capture vars after `f` failed.)
- **Check `j` (Honcho `:5432`) is unsatisfiable by the scripted core.** Honcho is
  out-of-repo (ADR 0004) and not installed by this contract; the gate ends at
  `FAIL:j` until the Step 2 tail brings Honcho up. All other checks pass on the
  bare scripted core. Open question: whether Honcho should join the scripted
  core (then the gate is fully satisfiable) or remain tail-verified.

## Prototype correction #2 — Honcho joins the deploy contract (D-A/D-E/D-D, 2026-08-04)

The #77 open question is resolved: Honcho joins the repo as a scripted,
idempotent deploy, and smoke gate `j` is now satisfiable.

- **D-A — deploy path.** Self-hosted Honcho v3.0.12 (`plastic-labs/honcho`,
  tag `v3.0.12`, commit `5ad22840`) at `/opt/honcho`, installed with `uv`,
  using the **third logical DB `honcho` on the existing Postgres 16 `:5433`**
  (`DB_CONNECTION_URI=postgresql+psycopg://honcho_app:…@127.0.0.1:5433/honcho`),
  systemd units `honcho-api.service` (`:8000`, uvicorn) and
  `honcho-deriver.service`, no Redis (in-memory cache). Docker Compose and a
  second Postgres cluster are rejected (ADR 0003/0004 alignment; smallest
  footprint on 12 GB; one instance to back up). ARM64 build verified PASS on
  the Ampere A1 target.
- **D-D — Deriver LLM.** MiniMax-M3 satisfies Honcho's tool-calling deriver
  contract via the OpenAI-compatible endpoint (`api.minimax.chat/v1`),
  **conditional on `DERIVER_MODEL_CONFIG__STRUCTURED_OUTPUT_MODE=json_object`**
  — MiniMax does not honor `response_format=json_schema`. Caveat: MiniMax
  `<think>…` reasoning preambles are not stripped by Honcho and consume
  output budget.
- **Smoke `j` amendment.** The Docker-era `ss … :5432` probe is replaced by a
  `curl /health` check on `127.0.0.1:8000` (with a `/dev/tcp` fallback). The
  gate is now fully satisfiable by the repo: `setup/honcho.sh` brings Honcho
  up idempotently (clone → `uv sync` → DB role/DB/extension → env from
  `setup/honcho/honcho.env.example` → units → alembic → workspace/peer
  provisioning via `setup/honcho-workspaces.py`). Wiring `honcho.sh` as an
  install.sh phase is deferred to the gateway tail (Task 5) so the install
  contract changes once.
- **Isolation verification (ADR 0004 gap).** `setup/honcho-workspaces.py`
  provisions `hermes_<persona>` workspace + peer per profile (get-or-create),
  matching `hermes/profiles/config.py` `generate_honcho_json()` exactly — the
  five workspace-level isolation boundary is now enforced server-side, and
  `tests/test_honcho_isolation.py` verifies the config side.

## Prototype correction #3 — gateway tail shipped in-repo (D-B fork 2, 2026-08-04)

The D4 acceptance items 2–3 (gateway up + systemd-enabled; three Discord
bots answer @-mention) are now served by this repo's own runtime:

- `hermes_agent/` — the rebuilt gateway (ADR 0004 amendment): multiplex
  Discord adapters (assistant/tutor/main_agent), FastMCP server with the six
  coding-agent tools, jobs.json cron scheduler, per-persona Honcho memory
  client, MiniMax-M3 LLM client (json_object mode, D-D pin).
- `setup/gateway.sh` + `setup/systemd/hermes-gateway.service` — idempotent
  bring-up: `/opt/hermes-gateway` venv, `pip install -e .`, plan_provision
  profile apply, unit install + enable. Bring-up stays in Step 2 (unscripted
  tail → now repo-scripted); install.sh phase list is unchanged.
- `DISCORD_ALLOWED_USER_ID` joins the REQUIRED key set (same allowlist for
  all three bots, CONTEXT.md: Discord home channel) — .env.example,
  install.sh, and setup/gateway.sh all validate it.
- CONTEXT.md "Contract gate integration" term updated: `hermes.personas` is
  imported by this repo's runtime, not an external hermes-agent.
- Acceptance mapping: gateway up + enabled → `hermes-gateway.service`;
  3 bots answer @-mention → bot loop proven on the VM (tokens are REQUIRED
  in .env; no auto-generation).
