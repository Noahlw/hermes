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
