# Hermes install runbook

This is the single entry point for bringing up a fresh Hermes VM. The
scripted phases are chained by `setup/install.sh`; this runbook carries
the unscripted tail and the operator-supplied prerequisites.

Authoritative contract: [ADR 0005 — install contract](./docs/adr/0005-hermes-reboot-install-contract.md).
Target environment: [ADR 0006 — target environment](./docs/adr/0006-hermes-reboot-target-environment.md).
Fresh-install inventory: [docs/research/2026-08-04-fresh-install-inventory.md](./docs/research/2026-08-04-fresh-install-inventory.md).
Gateway/profile wiring (unscripted tail): [ADR 0004 — agent integration model](./docs/adr/0004-hermes-agent-integration-model.md).

## Step 0 — prerequisites

Do this before any script runs.

### 0.1 Create the VM (manual, Oracle Cloud console)

The repo does not automate VM creation (ADR 0006 D3 — manual, no OCI
credentials in the repo). In the Oracle Cloud console:

1. Create a **VM.Standard.A1.Flex** instance (Ampere A1, ARM).
2. Shape: **2 OCPU / 12 GB RAM** (the E2.1.Micro 1 GB free tier cannot
   hold the stack).
3. Image: **Canonical Ubuntu 24.04 LTS Minimal (aarch64)** (Oracle
   Linux 9 is rejected — it would force porting every apt-based
   provision script to dnf + PGDG).
4. SSH in as `ubuntu`.

### 0.2 Verify the OS baseline

Run on the VM before anything else:

```bash
. /etc/os-release && echo "${ID} ${VERSION_ID} $(uname -m)"
```

Expected output: `ubuntu 24.04 aarch64`. `setup/install.sh` will fail
fast with a named error if this is anything else.

### 0.3 Install and authenticate Tailscale

Hermes services are reachable on the Tailscale mesh only (CONTEXT.md:
Tailscale-internal surface). No public exposure.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

The operator must supply the auth key (or complete interactive login).

### 0.4 Operator-supplied credentials

Before cloning, gather these values — `setup/install.sh` fails fast if
any REQUIRED key is empty in `.env`:

| Key | Source |
| --- | --- |
| `DISCORD_BOT_TOKEN_ASSISTANT` | Discord Developer Portal → Assistant bot |
| `DISCORD_BOT_TOKEN_TUTOR` | Discord Developer Portal → Tutor bot |
| `DISCORD_BOT_TOKEN_MAIN_AGENT` | Discord Developer Portal → Main Agent bot |
| `MINIMAX_API_KEY` | MiniMax-M3 API key (CONTEXT.md: MiniMax-only) |
| `DISCORD_HOME_CHANNEL` | The single Discord channel id all three bots listen on (CONTEXT.md: Discord home channel) |
| `HERMES_HOME` | The install path on this VM (e.g. `/home/ubuntu/hermes`) |

DR-only keys (`RESTORE_KEY_PATH`, `RCLONE_CONFIG_PATH`,
`AGE_IDENTITY_PATH`, `DRIVE_FOLDER_ID`): leave empty on a zero-data
fresh install. The Drive backup was never built (ADR 0005 D3), so the
restore phase is skipped by default.

## Step 1 — repo-driven install (scripted)

These phases are deterministic and chained by `setup/install.sh`. The
script halts on the first failing smoke; **redo = re-run from the top**
— the chained scripts are idempotent by design (ADR 0005 D2).

### 1.1 Clone the repo

```bash
git clone https://github.com/Noahlw/hermes.git "${HERMES_HOME}"
cd "${HERMES_HOME}"
```

Pick the path you wrote into `HERMES_HOME` in Step 0.4. Do not put the
clone somewhere else — `provision-indexer.sh` derives its working
directory from `HERMES_HOME`.

### 1.2 Create `.env`

```bash
cp .env.example .env
# edit .env — fill every REQUIRED key
```

Every REQUIRED key listed in `.env.example` is validated by
`setup/install.sh` phase 1. Missing keys produce a fail-fast message
that names them.

### 1.3 Run the scripted install

```bash
bash setup/install.sh
```

What it chains, in order (ADR 0005 D1, ADR 0006):

- **Phase 0** — preflight: OS is Ubuntu 24.04 aarch64; every
  `scripts/vm/*.sh` referenced in phase 2-5 exists.
- **Phase 1** — `.env` present; every REQUIRED key is non-empty.
- **Phase 2** — `scripts/vm/provision-hermes-postgres.sh`: apt-installs
  `postgresql-16` + `postgresql-16-pgvector`, configures Hermes
  Postgres on `127.0.0.1:5433` (Honcho shares this instance as the
  third logical DB `honcho`, D-A 2026-08-04),
  creates the `hermes` + `codebase_index` databases and roles.
- **Phase 3** — `db/migrate.sh` applies both schemas: `hermes` as
  `hermes_app`, `codebase_index` as `codebase_index_app` (the owner
  roles; `migrate.sh`'s `$USER` default lacks DDL rights). The
  pgvector extension is created once as `postgres` over the peer-auth
  unix socket — `CREATE EXTENSION` is superuser-only (prototype #77
  finding: the pre-fix chain never applied migrations at all).
- **Phase 4** — `scripts/vm/provision-indexer.sh`: apt-installs git +
  Python venv + `postgresql-client-16`; creates `indexer/config.json`;
  installs `hermes-indexer-webhook.service` and
  `hermes-indexer-reconcile.{service,timer}`; its own `db/migrate.sh
  codebase_index` call no-ops (schema applied in phase 3).
- **Phase 5** — `scripts/vm/smoke-hermes-postgres.sh`: round-trip
  probes on both databases; pgvector 768-dim zero-vector insert;
  schema_meta pins; Honcho API `/health` on `127.0.0.1:8000` (was the
  Docker-era `:5432` socket probe — amended 2026-08-04, ADR 0005
  addendum #2). **Hard gate** — halt on any `FAIL:<letters>`. The gate
  is fully satisfiable once Honcho is up (Step 2.6 brings it up via
  `setup/honcho.sh`); a bare scripted core without Honcho ends at
  `FAIL:j`.
- **Phase 6** — optional Drive restore. **Only runs if
  `RESTORE_KEY_PATH` is set in `.env`.** Calls
  `restore_postgres_drive.sh "$RESTORE_KEY_PATH"` then
  `smoke-restore.sh "$RESTORE_KEY_PATH"`. This is the DR tier; it is
  **unverified** end-to-end per ADR 0005 D3 (prototype #77 dry-runs
  it before it can be trusted). On a zero-data fresh install, leave
  `RESTORE_KEY_PATH` empty and the phase is skipped.

The script logs every phase with clear `[install.sh]` markers and
halts on the first failure. No new idempotency machinery is built; the
chained scripts already gate themselves on existence/markers.

### 1.4 Redo

Re-run from the top:

```bash
bash setup/install.sh
```

The chained scripts are idempotent (`provision-hermes-postgres.sh`
header: "Idempotent on every run"; `provision-indexer.sh` re-checks
config and migration state). Re-clone if the script or `.env.example`
itself changed between attempts.

## Step 2 — unscripted tail

Almost everything below is **not** in this repo. The repo supplies the
contract and the policy code; the agent brings the runtime. The one
exception: §2.6 Honcho — since 2026-08-04 (D-A/D-E) its deploy script
and templates live in-repo (`setup/honcho.sh`, `setup/honcho/`).

### 2.1 hermes-agent gateway + hermes-gateway.service

`hermes-agent` (NousResearch v0.15.1, [ADR 0004](./docs/adr/0004-hermes-agent-integration-model.md))
is **not** packaged by this repo. Bring up its venv and
`hermes-gateway.service` on the VM out-of-band. The integration seam
this repo relies on is the `pre_gateway_dispatch` plugin hook — see
ADR 0004 for the verified call site and the gateway's profile
multiplexing model (one `HERMES_HOME` per persona, same-token reuse
explicitly refused).

### 2.2 5-profile provisioning

ADR 0004 D: five hermes-agent profiles are provisioned —
`main_agent`, `assistant`, `tutor` (Discord-enabled via multiplex),
`librarian`, `researcher` (MCP-only, no Discord platform enabled).
The planning step (read-only, prints the apply commands) lives in this
repo:

```bash
python3 -m hermes.profiles.provision plan
```

Apply is a manual operator decision (do not pipe to apply
unattended — profile provisioning affects live Discord tokens).

### 2.3 cron registration

Hermes's cron is hermes-agent's `InProcessCronScheduler` over
`cron/jobs.json` — the VM's existing cron, not a parallel system
(ADR 0004 C). The template (rewritten 2026-08-04, map #76 Task 6)
already drops the legacy jobs whose scripts died with the old VM
(`vm-health-check` → `hermes-health-check`, `weekly-workspace-cleanup`
removed) and suspends `ollama-keep-alive` (see Step 2.5). Review
`cron/jobs.json` before activating — every remaining command must
resolve under `$HERMES_HOME` (`/home/ubuntu/hermes`) on this VM.

### 2.4 Library/cron regeneration

After profiles exist, regenerate any per-profile library files and
re-confirm the cron jobs land in the right `HERMES_HOME`.

### 2.5 Ollama is **not** installed

The target is Oracle Cloud free tier (2 CPU / 12 GB RAM); Ollama
cannot run there (ADR 0005 D4, ADR 0006 C). The schema pins
`vector(768)` / `nomic-embed-text` and the `ollama-keep-alive` cron
entry are **suspended** in the `cron/jobs.json` template (2026-08-04,
map #76 Task 6) until the embedding-provider decision (#43/#38)
lands. Do not install Ollama on this VM. The smoke script verifies
the 768-dim contract exists; the actual embedding host is TBD.

### 2.6 Honcho (self-hosted memory backend)

Brings Honcho v3.0.12 up on the shared Postgres `:5433` (third logical
DB `honcho`) with systemd API (`:8000`) + Deriver units, then
provisions the five persona workspaces/peers:

```bash
bash setup/honcho.sh            # idempotent; re-run safe
```

Env contract + unit templates live in `setup/honcho/` (`honcho.env.example`,
`honcho-api.service`, `honcho-deriver.service`); the deploy script fills
DB + LLM placeholders from the repo root `.env` on first run. The Deriver
uses MiniMax-M3 via its OpenAI-compatible endpoint (D-D gate, verified
2026-08-04 — `json_object` structured mode required). The embedding
provider stays unresolved (D-C / #43).

## Step 3 — acceptance checklist

ADR 0005 D4 — "working Hermes" = all of:

- [ ] `bash scripts/vm/smoke-hermes-postgres.sh` passes (`ALL_PASS`).
      (Requires Honcho up via Step 2.6; without it the gate ends at
      `FAIL:j`.)
- [ ] `hermes-gateway.service` is up and `systemctl is-enabled` returns
      `enabled`.
- [ ] All three Discord bots (Assistant, Tutor, Main Agent) answer an
      `@-mention` on `DISCORD_HOME_CHANNEL`.
- [ ] Cron jobs from `cron/jobs.json` are registered in the active
      hermes-agent profile.
- [ ] Indexer completes a first sync (`python -m hermes.indexer
      first-index owner/repo` for at least one allowlisted repo).
- [ ] `library_search` returns the MCP envelope (`ok: true` + `hits`).
- [ ] `.env` validation clean — `setup/install.sh` phase 1 reports
      no missing keys.

Ollama is excluded from acceptance until the embedding-provider
decision lands.

## Path notes

`scripts/vm/*.sh` hard-default `HERMES_HOME` to `/home/ubuntu/.hermes`
from the pre-reboot setup. They honor an exported `HERMES_HOME`, and
`setup/install.sh` exports it from your `.env` at the top of phase 1.
Use the real path you cloned at (Step 1.1) in `HERMES_HOME`; the
historical defaults inside the chained scripts are left alone
(ADR 0005 D1: scripts run unmodified on the chosen baseline).