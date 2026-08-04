# Hermes VM Configuration + Honcho Memory Backend Implementation Plan

> **For OMP workers:** Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch each task as a fresh `task` subagent; gate between tasks with the OMP `reviewer` agent (the `code-review` skill's spec axis).

**Goal:** Configure the fresh Ubuntu 24.04 aarch64 VM (`hermes`, Oracle Ampere A1 2 OCPU/12 GB, Tailscale-only) into a working Hermes per ADR 0005 D4 acceptance — with Honcho (plastic-labs/honcho v3) as the five-persona working-memory backend — and record every remaining contract gap.

**Architecture:** The scripted core of ADR 0005 is proven on the VM (install.sh phases 0–5; only smoke `j` fails pending Honcho). This plan closes the rest: land the unmerged persona runtime (profiles + Honcho isolation verifier), deploy Honcho self-hosted pointing at the existing Postgres 16 instance (`:5433`, pgvector — no second DB, no Docker, no Redis), provision five isolated workspaces/peers, amend the `j` smoke check from "5432 listening" to "Honcho API healthy", bring up the gateway tail, rewrite cron, first-sync the indexer, and dry-run the unverified DR chain.

**Tech Stack:** bash (existing scripts/vm/*), Honcho v3.0.12 server (FastAPI, AGPL-3.0) + honcho-ai SDK 2.2.0 (Apache-2.0), systemd, Postgres 16 + pgvector, uv ≥0.5, MiniMax OpenAI-compatible endpoint (deriver LLM — verify), Tailscale.

## Global Constraints

- Target: Ubuntu 24.04 LTS aarch64, Oracle Ampere A1, 2 OCPU / 12 GB (ADR 0006).
- **No Ollama.** Embedding provider is an open product decision (#43) — indexer first sync is gated on it; `vector(768)`/`nomic-embed-text` schema pins stay suspended.
- Tailscale only; **zero public exposure**; no OCI tooling/credentials (ADR 0006 D3).
- MiniMax-M3 only as LLM provider; MCP is the consumer surface.
- ADR 0003/0004: Hermes Postgres via apt/systemd, **not Docker** — same posture extends to Honcho's database (this plan) unless the user chooses otherwise.
- Existing scripts run unmodified except documented, review-gated amendments (ADR 0005 D1; the smoke `j` amendment is one).
- Secrets: template-driven `.env`; never commit secrets; age-key/Drive chain stays DR-only until #77 dry-run proves it.

## File Structure & Changes

- Create: `setup/honcho.sh` (Honcho deploy + systemd units + idempotent workspace/peer provisioning — or `setup/honcho/` split if it outgrows one file)
- Create: `setup/honcho-workspaces.py` (idempotent 5-workspace/peer provisioning via honcho-ai SDK)
- Modify: `scripts/vm/smoke-hermes-postgres.sh` (check `j`: replace `:5432` ss probe with Honcho `/health` probe — contract amendment, reviewer-gated)
- Modify: `cron/jobs.json` (HERMES_HOME paths; drop dead `vm-health-check`/`weekly-workspace-cleanup` or repoint; keep backup job; suspend `ollama-keep-alive`; add Honcho/Postgres health job)
- Modify: `INSTALL.md` Step 2 (Honcho bring-up, gateway tail, cron) — fills the documented gap
- Modify: `.env.example` (Honcho keys: `HONCHO_BASE_URL`, `HONCHO_DB_URI` optional, `LLM_*` key note; keep DR-only keys)
- Modify: `docs/adr/0005-hermes-reboot-install-contract.md` (addendum: Honcho in scripted core, `j` amendment, backup-set note)
- Modify: `docs/runbooks/fresh-vm-restore.md` (Honcho now third logical DB on `:5433`, `honcho.dump` from same instance)
- VM files: `/etc/systemd/system/honcho-api.service`, `honcho-deriver.service`, `/home/ubuntu/hermes/.env` (extended), Honcho source tree at `/opt/honcho` (or `$HERMES_HOME/honcho`)

## What Already Exists

- `setup/install.sh` phases 0–5 proven on the VM (migrations + indexer-before-smoke fixed in PR #84).
- `hermes/profiles/config.py` + `hermes/honcho/isolation.py` (unmerged, ticket-62-runtime-wiring, commit `5192bd4`) — generate per-profile config/honcho.json and verify workspace/peer distinctness.
- `cron/jobs.json` (5 jobs, 2 dead, 1 suspended), `scripts/vm/backup_postgres_drive.sh` + restore chain, `db/migrate.sh`.
- Honcho research note `/tmp/honcho-research.md` (primary sources; v3.0.12; DB_CONNECTION_URI shape; no official ARM64 guarantee → staging smoke required).

## Not In Scope

- #43 embedding-provider decision itself (this plan only gates on it).
- Rebuilding hermes-agent gateway internals (ADR 0004: repo is the policy layer, gateway is the runtime — locating/obtaining the gateway is decision D-B).
- Monitoring dashboards (#45 strategy stays a separate ticket).
- Honcho managed SaaS (api.honcho.dev) — self-host per standing preferences.

## ASCII Diagram

```
Mac (coding agent, MCP consumer) ──Tailscale──▶ VM hermes (Ubuntu 24.04 aarch64)
                                                 │
            ┌────────────────────────────────────┼────────────────────────────┐
            ▼                                    ▼                            ▼
   hermes-agent gateway              Honcho v3 (uv, systemd)          cron (InProcess)
   (3 Discord profiles +            API :8000  +  Deriver  ─┐         5 jobs (rewritten)
    2 MCP profiles,                  │  DB_CONNECTION_URI    │
    multiplex_profiles)              ▼                       │
            │              ┌────────┴─────────┐              │
            │              │ Postgres 16 :5433│◀─────────────┘
            └─────────────▶│  hermes (app)    │   (pgvector ext)
                           │  codebase_index  │
                           │  honcho (new DB) │
                           └──────────────────┘
   smoke gate j: ss :5432  →  Honcho /health :8000 (amendment)
```

## Failure Modes & Gaps

- **ARM64 unverified**: Honcho builds from source; no official aarch64 guarantee. Mitigation: Task 2 staging build + `/health` + workspace create BEFORE any systemd wiring.
- **Deriver LLM compat**: Honcho requires a tool-calling LLM; default config OpenAI-compatible. MiniMax-M3 OpenAI-compatible endpoint must be verified (custom `base_url` support in Honcho config). Fallback: another provider key, or Deriver degraded mode — decision D-D.
- **Gateway source unknown**: hermes-agent is not in this repo and the old VM is gone. If the user cannot supply it, D4 bot acceptance cannot be met by this plan — surface early (D-B), do not silently rebuild.
- **Embedding provider (#43)**: indexer first sync blocked; k/l pins remain suspended — acceptance checklist item 5 (indexer first sync) may fail until decided.
- **Smoke `j` amendment**: changing a legacy script violates "run unmodified" — must be a reviewer-gated contract amendment recorded in ADR 0005, not a silent edit.
- **Honcho DB backups**: third logical DB must join the Drive backup set (backup script config) or DR is incomplete.

## Parallelization / Worktree Strategy

Task 1 (persona branch PR) and Task 2 (Honcho staging on VM) are independent — can run in parallel. Tasks 3–9 are sequential on the VM after their gates. Use a dedicated worktree for repo-side tasks (Task 1, smoke amendment, cron rewrite, docs); VM work runs directly over SSH.

---

## Decision Gates (close with the user before Task 3)

- **D-A — Honcho deploy path — ADOPTED 2026-08-04:** manual `uv` install, Honcho DB = third logical DB (`honcho`) on the existing Postgres 16 `:5433` via `DB_CONNECTION_URI=postgresql+psycopg://…@127.0.0.1:5433/honcho`, systemd units for API + Deriver, no Redis (cache disabled by default). Rationale: ADR 0003/0004 alignment (no Docker for Postgres), one instance to back up, smallest footprint on 12 GB. (Alternatives rejected: Docker Compose adds engine + second Postgres; second cluster adds a second instance to manage.)
- **D-B — Gateway source — RESOLVED 2026-08-04 (fork 2):** hermes-agent is **lost** — verified absent from the VM (systemd/processes/dirs/pip/docker/history), from GitHub (only `hermes` + `efcc-scanner` repos), and from reachable Mac locations (Desktop artifacts are an unrelated agentmemory experiment). User confirmed only the GitHub repo + current VM remain. Decision: **rebuild a minimal gateway** from the repo's policy layer (`hermes/personas/`, profiles, adapters) — new runtime scope requiring an ADR 0004 amendment ("not a replacement runtime" → now the runtime). Sequenced as Task 5; infra tasks (1–4, 6–8) do not depend on it.
- **D-E — Honcho in scripted core — ADOPTED 2026-08-04:** `setup/honcho.sh` becomes an install.sh phase; smoke gate fully satisfiable; ADR 0005 open question closed.
- **D-C — Embedding provider (#43).** Decision gates Task 7 (indexer first sync). While open, acceptance item 5 stays red by design.
- **D-D — Honcho deriver LLM.** Verify MiniMax OpenAI-compatible endpoint works as Honcho's LLM provider (tool-calling required). If not, pick a provider or accept degraded Honcho (no observations/conclusions) — then smoke `j`-adjacent checks must reflect that.
- **D-E — Honcho in scripted core.** Recommended: yes — `setup/honcho.sh` becomes a new install.sh phase so the smoke gate is fully satisfiable and the ADR 0005 open question closes. Alternative: keep tail-only (gate stays red until manual bring-up).

---

### Task 1: Land the persona runtime (ticket-62-runtime-wiring → PR)

**Files:** whole `ticket-62-runtime-wiring` branch diff vs master (13 files: `hermes/profiles/*`, `hermes/honcho/*`, `hermes/digest/*`, `hermes/hermes_agent_plugin/confirm_delete.py`, `db/hermes/migrations/0002_digests.sql`, 4 test files, CONTEXT.md glossary lines).

**OMP dispatch:** `task` subagent; reviewer gate (spec axis: ADR 0004, ticket #62/#66–#69/#71–#74 dispositions).

- [ ] **Step 1:** Open PR from `ticket-62-runtime-wiring` to `master` (branch exists; user's main checkout is on it — do not move it, create the PR from the remote branch).
- [ ] **Step 2:** Reviewer verifies: profiles generator produces distinct `honcho.json` `workspace_id`/`ai_peer` per persona; isolation verifier tests pass; digest migration `0002_digests.sql` applies via `db/migrate.sh hermes`; no VM-era paths (`/home/ubuntu/.hermes`) introduced.
- [ ] **Step 3:** Merge (user approves). Update dispositions #62/#66–#69/#71–#74 (retained → landed).
- [ ] **Step 4:** On VM: `git pull`, run `pytest` (expect 356 passing — proves in-situ).

**Acceptance:** master contains the persona runtime; VM pytest 356 green.

### Task 2: Honcho staging build + ARM64 smoke (VM)

**Files:** none (scratch under `/tmp` or `/opt/honcho-staging`).

- [ ] **Step 1:** `apt-get install -y uv` (or install uv ≥0.5 per official script); `git clone -b v3.0.12 https://github.com/plastic-labs/honcho.git`.
- [ ] **Step 2:** `uv sync` in the repo (server deps) — record any ARM64 build failures verbatim.
- [ ] **Step 3:** Create `honcho` DB + role on `:5433` (`CREATE ROLE honcho_app LOGIN; CREATE DATABASE honcho OWNER honcho_app;`), `CREATE EXTENSION vector` (superuser), set `DB_CONNECTION_URI` to the app role.
- [ ] **Step 4:** `uv run alembic upgrade head` against it — must apply cleanly (this also validates the external-PG path from the research note).
- [ ] **Step 5:** Start API + Deriver briefly with a test LLM key; `curl localhost:8000/health` → ok; `POST /v3/workspaces` → 201. Stop.
- [ ] **Step 6:** Record findings on #77 (ARM64 verdict, version pin v3.0.12, env vars used).

**Acceptance:** Honcho v3.0.12 builds and runs on aarch64; external-PG-on-5433 path proven; exact env var names recorded.

### Task 3: Honcho deploy (per D-A) + systemd

**Files:** VM: `/opt/honcho` (source checkout v3.0.12, `uv sync` — venv), `/etc/systemd/system/honcho-api.service`, `honcho-deriver.service` (Restart=on-failure, sandboxing basics), `.env` additions; repo: `.env.example` Honcho block.

- [ ] **Step 1:** Move staging install to `/opt/honcho`; write DB role creds into `/opt/honcho/.env` (mode 600) or reference `$HERMES_HOME/.env` keys (`HONCHO_DB_URI`, `HONCHO_LLM_*` per Task 2 findings).
- [ ] **Step 2:** Write both systemd units (API: `uv run uvicorn honcho.main:app --host 127.0.0.1 --port 8000`; Deriver: worker command from Task 2 record). Enable + start.
- [ ] **Step 3:** Verify: `systemctl is-active honcho-api honcho-deriver`, `curl 127.0.0.1:8000/health`, `ss -tln | grep :8000`. Idempotent re-run via `systemctl restart`.
- [ ] **Step 4:** Record env-var contract + unit contents in `INSTALL.md` Step 2 (fill the gap) and `.env.example`; commit docs on repo side.

**Acceptance:** Honcho API + Deriver stable under systemd, health green, documented.

### Task 4: Workspaces/peers provisioning + smoke `j` amendment

**Files:** repo: `setup/honcho-workspaces.py` (idempotent), `scripts/vm/smoke-hermes-postgres.sh` (check `j` amendment), `docs/adr/0005` addendum.

- [ ] **Step 1:** Write `setup/honcho-workspaces.py` using `honcho-ai` 2.2.0 (sync client, `base_url=http://127.0.0.1:8000`): for each of `main_agent, assistant, tutor, librarian, researcher` — upsert workspace `hermes-<persona>` and peer `ai_peer` id (exact ids from `hermes/profiles/config.py` `generate_honcho_json`); idempotent (GET-or-create); exit non-zero on failure.
- [ ] **Step 2:** Run it on the VM against live Honcho; then run the isolation check: `python -m pytest tests/test_honcho_isolation.py` (from Task 1) — must pass (distinct peers/workspaces proven against the real backend, not just config).
- [ ] **Step 3:** Amend smoke `j`: replace `ss … :5432` probe with `curl -fsS http://127.0.0.1:8000/health` (or honcho health via psql to `honcho` DB as fallback). Update INSTALL.md phase-5 text + ADR 0005 addendum (reviewer gate: contract amendment).
- [ ] **Step 4:** Full re-run: `bash setup/install.sh` → smoke gate **ALL_PASS** (first time in reboot history).

**Acceptance:** 5 workspaces/peers exist; isolation verifier green against the backend; `install.sh` reaches `ALL_PASS`.

### Task 5: Gateway tail (per D-B) — profiles apply + bots
### Task 5: Gateway rebuild (D-B fork 2) — minimal hermes-agent runtime

**Context:** The original `hermes-agent` (Discord adapters, MCP server, InProcessCronScheduler, Honcho client, profile multiplexing) is lost. Rebuild the minimal runtime that imports this repo's policy layer (`hermes/personas/` — `route_discord_message()` / `route_mcp_tool()`, `pre_gateway_dispatch` hook, `ExecApprovalView` pattern per CONTEXT.md) and honors ADR 0004's integration model. **Requires an ADR 0004 amendment** ("not a replacement runtime" → this repo's `hermes-agent` IS the runtime) — reviewer-gated.

**Files (new):** `hermes_agent/` package — `main.py` (multiplex gateway), `discord_adapter.py` (3 bot tokens, home channel, @-mention gate, ExecApprovalView), `mcp_server.py` (named read tools per CONTEXT.md: `library_search`, `session_brief`, `conduct_research`, `knowledge_catalog`, `expand_citation`, `impact_map` — policy calls into `hermes/personas/`), `cron_scheduler.py` (jobs.json), `honcho_client.py` (5 peers/workspaces), `profiles/` wiring (config.yaml + honcho.json per persona); `setup/gateway.sh`; systemd unit `hermes-gateway.service`; VM per-profile dirs.

- [ ] **Step 1 (ADR amendment):** ADR 0004 addendum — repo's `hermes-agent` becomes the V1 runtime; policy-layer contract unchanged. Reviewer gate.
- [ ] **Step 2:** Multiplex gateway skeleton: load 5 profiles (PROFILE_DEFINITIONS), route by mention/tool, `pre_gateway_dispatch` hook; tests for routing per CONTEXT.md contract.
- [ ] **Step 3:** Discord adapter: 3 bots, home channel, required-mention gate, ExecApprovalView confirm pattern (per CONTEXT.md confirm_delete UX); tests.
- [ ] **Step 4:** MCP server: 6 named read tools routed via `route_mcp_tool()`; `library_search` returns the D4 envelope (`ok: true`); tests.
- [ ] **Step 5:** Cron scheduler (InProcessCronScheduler semantics, jobs.json) + Honcho client (peers per Task 4 workspace ids); tests.
- [ ] **Step 6:** `setup/gateway.sh` + systemd unit; install on VM; 3 bots answer @-mention; D4 acceptance items 2–3 green.

**Acceptance:** gateway up + systemd-enabled; 3 bots answer @-mention (ADR 0005 D4 items 2–3).

### Task 6: Cron rewrite + registration

**Files:** repo: `cron/jobs.json`; VM: jobs registered via gateway cron scheduler (or crontab per gateway model).

- [ ] **Step 1:** Rewrite `jobs.json`: paths `$HERMES_HOME`-relative (`/home/ubuntu/hermes/…`); drop `vm-health-check` (script missing) → replace with new `hermes-health-check` job calling a real health script (Task 9 suggestion; ports + systemd + tailscale status → log); drop `weekly-workspace-cleanup` (script missing) or repoint; keep `portable-postgres-backup` (`--weekly`); keep `neo4j-drive-backup` disabled; suspend `ollama-keep-alive` (pending #43).
- [ ] **Step 2:** Register on VM; verify schedule listing + one forced run of the backup job (dry-run mode if supported).
- [ ] **Step 3:** Update INSTALL.md Step 2 cron section; commit.

**Acceptance:** `jobs.json` contains only live jobs with valid paths; registration verified; backup job executes (see Task 8 for restore side).

### Task 7: Indexer first sync (gated on D-C)

**Files:** VM: `indexer/config.json`, allowlist entry; repo: README/INSTALL wording if needed.

- [ ] **Step 1:** (After D-C) Add allowlist entry + `python -m hermes.indexer first-index owner/repo` for the Hermes repo (and any user repos).
- [ ] **Step 2:** Verify `library_search` MCP envelope `ok: true` with hits (acceptance item 6).
- [ ] **Step 3:** Confirm `schema_meta` pins match the decided provider (migration may need a follow-up amendment).

**Acceptance:** indexer first sync done; `library_search` ok; acceptance items 5–6 green.

### Task 8: DR dry-run (unverified chain, ADR 0005 D3)

**Files:** VM: age key at operator-chosen path, `key-bootstrap.sh` → `encrypt-secrets.sh` → `backup_postgres_drive.sh` → `restore_postgres_drive.sh` → `smoke-restore.sh`; repo: runbook updates (fresh-vm-restore.md).

- [ ] **Step 1:** Ensure backup script covers the `honcho` DB (third logical DB on `:5433`; update config/dump list; honcho.dump expected).
- [ ] **Step 2:** age key bootstrap (operator-owned; never upload key to Drive).
- [ ] **Step 3:** Run backup end-to-end (real small data), then restore into `_smoke` DBs (per fresh-vm-restore.md §"Smoke restore"), verify rows, drop.
- [ ] **Step 4:** Record verdict on #77 (chain trusted or not) + update ADR 0005 D3 wording from "unverified" to result.

**Acceptance:** backup → restore → verify cycle passes with real data; verdict recorded.

### Task 9: Final acceptance + hardening suggestions

**Files:** repo: INSTALL.md Step 3 checklist final state; ADR 0005 addendum.

- [ ] **Step 1:** Run INSTALL.md Step 3 checklist: smoke ALL_PASS; gateway up+enabled; 3 bots answer; cron registered; indexer synced; `library_search` ok; `.env` validation clean. (Items gated on D-B/D-C report status explicitly.)
- [ ] **Step 2:** Apply the agreed hardening (selected 2026-08-04; each as a separate step with verification):
  - **H1 (done 2026-08-04):** delete `~/.ssh/hermes-vm-leaked` from the Mac; verified the VM's
    `authorized_keys` contains only `ssh-key-2026-08-03` (fingerprint `SHA256:VM+90V5os…`,
    both sides).
  - **H2 — swap/zram:** add 2–4 GB zram (or swapfile); verify with `free -h` and `zramctl`.
  - **H3 — unattended-upgrades:** enable security-only auto-updates; verify `unattended-upgrades --dry-run`.
  - **H4 — OCI monitoring agent:** remove/disable `/opt/unified-monitoring-agent` (phones Oracle;
    zero-exposure posture); verify process gone after reboot.
  - **H5 — in-situ pytest:** `cd $HERMES_HOME && python3 -m pytest` → 356 passed (already
    exercised as Task 1 Step 4; re-run after every repo-side task).
  - **H6 — Honcho joins backup set:** `backup_postgres_drive.sh` dumps the `honcho` DB alongside
    `hermes`/`codebase_index` (Task 8 Step 1 verification).
- **Step 3:** Close #77 with the full prototype verdict; update map #76 children/decisions.

**Acceptance:** Checklist complete or explicitly gated; hardening applied; #77 closed with verdict.
