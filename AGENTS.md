# AGENTS.md — Hermes installer + extensions playbook

This repo (`Noahlw/hermes`) is the **installer and extension layer for the
official Hermes Agent** (`NousResearch/hermes-agent`). It does **not** ship a
runtime. A coding agent reads this file and follows it step by step to make a
VM run the official Hermes Agent with this repo's persona contracts, codebase
knowledge layer, and memory setup.

> Pivot: ADR 0007 (2026-08-05). The private gateway runtime (`hermes_agent/`)
> and its bespoke install contract are **archived** under `archive/` — do not
> resurrect them. History is preserved; only `archive/` is dead code.

---

## What this repo is

| Piece | Where | Role |
|---|---|---|
| Persona policy core | `hermes/personas/` (contract_gate, adapters, contracts) | hermes-agent-agnostic contract gate — the five personas, allowed actions, typed refusals |
| Upstream plugin adapter | `hermes/hermes_agent_plugin/` | `pre_gateway_dispatch` hook wiring that applies the gate inside hermes-agent |
| Codebase indexer | `hermes/indexer/` | Postgres + pgvector code knowledge layer; sync/parse/mirror/webhook; knowledge tools (`library_search` et al. — ported from `archive/hermes_agent/mcp_server.py`) |
| Digest formatter | `hermes/digest/` | cron/ops digest composition |
| Profile configs | `hermes/profiles/` | persona profile provisioning |
| Memory infra | `setup/ollama/`, `setup/honcho/` | Ollama embeddings (127.0.0.1:11434) + self-hosted Honcho API/deriver |
| Agent playbook | **this file** | the install + setup + verify runbook |
| Archived runtime | `archive/` | old private gateway, its tests, bespoke installers — reference only |

## Non-negotiable constraints

- **Runtime is official only**: installed via upstream's own installer, never
  via this repo's scripts.
- **MiniMax-M3 is the only LLM provider** (D-D). No other model provider.
- **Zero public exposure** (D3): nothing binds a public interface; all
  cross-PC traffic over Tailscale; MCP is the consumer surface.
- **No training/no-retention providers** (IDX-1): local Ollama embeddings and
  MiniMax only; never route source code to training-on-prompt providers.
- **Destructive ops need operator approval**: force-push, `git reset --hard`,
  DB drops, service decommissions — confirm with the operator every time.
- Reviewer gate: install-contract / ADR / PR changes are reviewed by the
  `Task5Review2` peer before merge (hub thread `154a1ddefc1414e2`).
- Never echo secrets (Discord tokens, API keys) into logs, commits, or chat.

---

# The playbook

Goal: on the target VM (`ubuntu@hermes`, Oracle Ampere A1, Ubuntu 24.04
aarch64), a fresh install of the official Hermes Agent, configured with this
repo's stack, verified by the 7-check gate, with the old private stack
decommissioned only after verification.

The steps below are written for a coding agent with SSH access to the VM
(`ssh -i ~/.ssh/hermes-vm-2026-08-03.key ubuntu@hermes`) and write access to
this repo. **Verify each step's output before proceeding.**

## Step 1 — Install the official Hermes Agent

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

What the official installer does (source-verified, v0.20.x):

- Installs its own `uv` at `~/.hermes/bin/uv`, Python 3.11, Node 22,
  npm/Playwright, and clones the agent to `~/.hermes/hermes-agent` (code +
  venv).
- Installs launchers: `~/.local/bin/hermes`, `hermes-agent`, `hermes-acp`.
  (Root installs go to `/usr/local/lib/hermes-agent` + `/usr/local/bin`.)
- Copies config templates and may run an interactive setup wizard
  (`hermes setup` on `/dev/tty`). On a headless VM, **skip or exit the wizard**
  — every setting is applied deterministically in Step 2 via config files and
  `hermes config set`, then `hermes doctor` confirms.

Verification: `hermes --version` and `hermes doctor` exist and run.
Note: `~/.hermes` is upstream's home. On a **fresh machine** the default
home is correct. On **this VM** (staged swap) `~/.hermes` already holds
live private-stack state (indexer config + mirrors, five per-persona
profile dirs) — install upstream into a separate home so the installer
never touches the running private stack:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- \
  --hermes-home ~/.hermes-official
```

`~/.hermes-official` is upstream's home on this VM until Step 5 frees
`~/.hermes` of private state.

The installer's `--hermes-home` flag sets the *install* directory but does
**not** persist `HERMES_HOME` for the runtime — the CLI defaults to
`~/.hermes` unless the env var is exported. Set it in the shell profile
(`~/.bashrc`) and pass it to every service/systemd invocation:

```bash
export HERMES_HOME="$HOME/.hermes-official"
```

## Step 2 — Configure the runtime

All paths are under `~/.hermes/` (i.e. `~/.hermes-official/` on this VM)
unless noted. Edits to `config.yaml` are first-class (upstream documents
direct config editing); restart services after editing.

### 2a. MiniMax-M3 provider (only LLM)

Upstream's `minimax` provider is a built-in model-provider plugin
(`plugins/model-providers/minimax/`). It is configured via
`model.provider` / `model.default` and the `MINIMAX_API_KEY` env var — the
old runtime's `providers:` block does not exist upstream. On this VM the
key is China-scoped to `api.minimax.chat`, so set the OpenAI-compatible
endpoint explicitly:

```bash
hermes config set model.provider minimax
hermes config set model.default MiniMax-M3
hermes config set model.base_url https://api.minimax.chat/v1
hermes config set model.api_mode chat_completions
```

Set `MINIMAX_API_KEY` in `~/.hermes/.env`. Verify:
`hermes config get model --json` and `hermes chat -q "reply with: ok"`.
Auxiliary slots stay `auto` (main model) unless a task needs a cheaper model.

> `hermes doctor`'s MiniMax health probe hits the hardcoded *global*
> endpoint `https://api.minimax.io/v1/models`, which a China-scoped
> `api.minimax.chat` key does not validate on — doctor flags
> "Check MINIMAX_API_KEY in .env" even though the configured endpoint
> works (the chat check is the ground truth). This is a cosmetic
> doctor false-positive, not a runtime problem.

### 2b. Profiles — the three Discord personas

Main Agent = **default profile** (plain `hermes`; owns CLI, ops, cron,
digests). Assistant and Tutor = named profiles, each with its own Discord
bot token and isolated memory.

```bash
hermes profile create assistant
hermes profile create tutor
```

Per profile, set the Discord bot token in its own secret scope:
`~/.hermes/profiles/<name>/.env` → `DISCORD_BOT_TOKEN=...` (upstream resolves
platform tokens under the active profile's scope; env map lives in
`gateway/config.py` — re-verify the key name against the installed version).

Discord is enabled by the presence of `DISCORD_BOT_TOKEN` in the profile's
`.env` (v0.20: `gateway/config.py` `_enable_from_env(Platform.DISCORD)`).
Set the home channel and the operator allowlist in the same scope:

```bash
# ~/.hermes/.env                        (default / Main Agent)
# ~/.hermes/profiles/<name>/.env        (assistant / tutor)
DISCORD_BOT_TOKEN=<unique per profile>
DISCORD_HOME_CHANNEL=<home channel id>
DISCORD_ALLOWED_USERS=<operator discord id>   # zero public exposure
```

Do **not** reuse the same token in two profiles (upstream fails fast on
token conflicts). The three existing bot tokens from the old stack carry over
1:1: Main Agent, Assistant, Tutor.

> During the staged swap the **private** gateway (`hermes-gateway.service`)
> still polls all three tokens. Starting an upstream gateway for a profile
> session-takes the same bot token from the private gateway (Discord kicks
> the older session). The private service stays active; the takeover is
> resolved at Step 5. The default-profile bot shares the Main Agent token
> with the live private gateway, so its @-mention test is operator-owned
> (defer starting the default gateway until Step 5).

### 2c. Memory — self-hosted Honcho + Ollama embeddings

Keep the VM's `honcho-api` + `honcho-deriver` + `ollama` (127.0.0.1:11434,
`nomic-embed-text`, 768-dim) running — they are the memory infra (D-C).
Upstream's Honcho provider is a plugin (`plugins/memory/honcho/`) that needs
the `honcho-ai` pip package installed into the upstream venv:

```bash
~/.hermes/hermes-agent/venv/bin/pip install "honcho-ai==2.2.*"
hermes config set memory.provider honcho
```

Then write `~/.hermes/honcho.json` pointing at the self-hosted API (local
URLs skip API-key auth; the VM's honcho-api runs `AUTH_USE_AUTH=false`):

```json
{
  "baseUrl": "http://127.0.0.1:<honcho-api-port>",
  "workspace": "hermes",
  "peerName": "<operator>",
  "hosts": {
    "hermes":       { "aiPeer": "main_agent", "recallMode": "hybrid" },
    "hermes_assistant": { "aiPeer": "assistant", "recallMode": "hybrid" },
    "hermes_tutor":     { "aiPeer": "tutor", "recallMode": "hybrid" }
  }
}
```

Host key = `hermes` (default) / `hermes_<profile>` (deduced from the active
profile; `plugins/memory/honcho/client.py` `profile_host_key`) — this gives
each persona its isolated peer memory (CONTEXT.md contract). Find the
honcho-api port with `systemctl cat honcho-api` / `ss -ltn`. Verify:
`hermes honcho status` shows the provider active; a chat turn lands in Honcho
(Step 4 check 5).

### 2d. Codebase knowledge tools (indexer)

The indexer stays a service on the VM (its own venv, Postgres
`codebase_index` with pgvector), and the knowledge tools
(`library_search`, `session_brief`, `knowledge_catalog`, `expand_citation`,
`impact_map`, `conduct_research`) are **ported from
`archive/hermes_agent/mcp_server.py`** into the extension layer (their
archived deps — `hermes_agent.llm` MiniMax client, `hermes_agent.config` —
are replaced by upstream's own model calls and plugin config; the DB access
is already `hermes.indexer`). Two consumption shapes, Q6:

1. **Native plugin tools** (full distribution — the primary shape): register
   each knowledge tool with `ctx.register_tool(...)` in the noahlw plugin.
   Tools are data-only (query the index, return JSON) — no LLM client needed;
   the agent's own model narrates with citations.
2. **MCP server** (for non-hermes consumers, e.g. coding agents over
   Tailscale): serve the same tools via an MCP endpoint bound to
   **127.0.0.1 or the Tailscale address only**
   (`hermes.indexer.mcp.create_knowledge_server(bind_host, port)`), and
   register it in `~/.hermes/config.yaml`:

   ```yaml
   mcp_servers:
     hermes-indexer:
       url: http://127.0.0.1:<indexer-mcp-port>/mcp
       headers:
         Authorization: "Bearer <local-token>"
   ```

Run a sync (`hermes-indexer sync` with the repo's allowlist config) so the
index is fresh before verification.

The webhook server binds **127.0.0.1 by default** (`IndexerConfig.webhook_host`,
zero public exposure, D3). Set `webhook_host` in config.json to a
private/Tailscale address only if GitHub webhook callbacks are needed;
otherwise the reconcile timer keeps the index fresh.

### 2e. Extension layer

1. **Install this repo into upstream's venv** (so `hermes.personas` +
   `hermes.hermes_agent_plugin` are importable by the plugin loader). On this
   VM the repo checkout is the worktree `~/.hermes-official` sibling
   `/home/ubuntu/hermes-official` (the private `/home/ubuntu/hermes` is the
   live pre-pivot checkout and must stay untouched):

   ```bash
   pip install -e /home/ubuntu/hermes-official \
     --python ~/.hermes/hermes-agent/venv/bin/python
   ```

   The repo's `pyproject.toml` must declare `requires-python = ">=3.11"`
   (not `>=3.12`) because upstream's venv is Python 3.11.
2. **Drop the plugin shim** — upstream discovers plugins at
   `~/.hermes/plugins/<name>/` (`plugin.yaml` + Python):

   `~/.hermes/plugins/noahlw/plugin.yaml`:
   ```yaml
   name: noahlw
   version: 0.1.0
   description: Persona contract gate + Hermes extension layer
   provides_tools:
     - library_search
     - knowledge_catalog
     - expand_citation
     - impact_map
     - session_brief
     - conduct_research
   provides_hooks:
     - pre_gateway_dispatch
   ```
   `~/.hermes/plugins/noahlw/__init__.py`:
   ```python
   from hermes.hermes_agent_plugin import register  # forwards to the gate
   ```
   Enable it (plugins are opt-in): `hermes plugins enable noahlw`.

   Upstream v0.20 plugin contract (verified against the installed
   `hermes_cli/plugins.py` + `tools/registry.py`):
   - `register(ctx)` is called with **only** the `PluginContext` — no
     per-profile overrides. The gate's `home_channel` is therefore read from
     the profile env (`DISCORD_HOME_CHANNEL` / `DISCORD_ALLOWED_USERS`) inside
     `hermes.hermes_agent_plugin`.
   - Tool handlers are invoked as `handler(args, **kwargs)` where `args` is
     the model-supplied argument dict. The repo's gated wrapper unpacks
     `args` into the indexer handlers' keyword parameters.
   - `plugin.yaml` uses comma-separated `provides_tools:` / `provides_hooks:`
     lists (not a single `provides_hooks: [pre_gateway_dispatch]` mapping).
   - `pre_gateway_dispatch` hook: plugins return action dicts
     `{"action": "skip"|"rewrite"|"allow", ...}`; internal events bypass the
     hook; `session_store` may be `None`. **Re-verify against the installed
     version** (`hermes_cli/plugins.py`, `tools/registry.py`) whenever
     `hermes update` bumps major/minor.
3. **Contract gate config** — the gate reads persona contracts from
   `hermes/personas/contracts/` and operator allowlists (home channel,
   allowed users) from the profile env. Gate behavior (Librarian/Researcher
   job contracts on MCP calls, Assistant/Tutor refusals) is unchanged from
   CONTEXT.md.
4. **Digest** — `hermes/digest/formatter.py` is a deterministic formatter.
   Schedule it via upstream's `hermes cron` with a `--no-agent --script`
   job that emits the digest markdown (see `scripts/` for the runner):
   ```bash
   hermes cron create "0 5 * * *" --name ops-digest \
     --script ops-digest.py --no-agent --deliver local
   ```
5. **Quick commands + personalities** — apply from the repo templates
   (`config.yaml` `quick_commands:` / `personalities:`).

### 2f. Scheduled jobs

Upstream ships its own cron scheduler (`hermes cron`). Port the digest to it
(Step 2e.4). The indexer reconcile runs as a **systemd timer**
(`hermes-indexer-reconcile.timer`, Step 3). The remaining old jobs
(health-check, ollama keep-alive, Postgres backup) run inside the **private
gateway's own InProcessCronScheduler** (`/home/ubuntu/hermes/cron/jobs.json`)
— they are **not** systemd timers and stay with the private gateway until
Step 5; do not re-create them upstream while the private stack runs.

## Step 3 — Relocate + provision the indexer out of `~/.hermes`

The indexer's XDG defaults (ADR 0007; `hermes/indexer/config.py`) are
`~/.config/hermes-indexer/config.json` and
`~/.local/share/hermes-indexer/mirrors` — never under `~/.hermes`. Move the
VM's pre-pivot state there and provision the indexer venv (on this VM the
indexer venv was never created — only the config existed):

```bash
mkdir -p ~/.config/hermes-indexer ~/.local/share/hermes-indexer
mv ~/.hermes/indexer/config.json ~/.config/hermes-indexer/config.json
mv ~/.hermes/mirrors ~/.local/share/hermes-indexer/mirrors
# edit config.json: mirrors_root -> ~/.local/share/hermes-indexer/mirrors
#   (tilde is expanded at load — d938f1a)

# provision the venv from this repo's worktree (d938f1a XDG code)
python3 -m venv ~/.local/share/hermes-indexer/venv
~/.local/share/hermes-indexer/venv/bin/pip install -e /home/ubuntu/hermes-official
```

Re-point the indexer systemd units at the moved config + venv
(`INDEXER_CONFIG`, `WorkingDirectory`, `ExecStart`), then
`systemctl daemon-reload` and start **only** the hermes-indexer units
(`hermes-indexer-webhook.service`, `hermes-indexer-reconcile.timer`).
Verify `hermes-indexer config-validate` and a `reconcile --once` run.

> The indexer must run from a working directory that does **not** contain a
> `hermes/` package (e.g. `/home/ubuntu`) — the private checkout
> `/home/ubuntu/hermes` shadows the installed `hermes` as a namespace
> package and breaks `python -m hermes.indexer`. Give the reconcile unit a
> `WorkingDirectory=/home/ubuntu/.local/share/hermes-indexer`.

`/opt/hermes-gateway` (old venv) and `/home/ubuntu/hermes` (repo checkout)
stay until Step 5; do not touch. The private gateway keeps reading its own
state from `~/.hermes/profiles/` until Step 5 — do not move those dirs
while it runs.

## Step 4 — Verification gate (all 7 must pass)

1. `hermes doctor` — clean (see the 2a note on the MiniMax probe
   false-positive).
2. `hermes chat -q "reply with exactly: ok"` — answers via MiniMax-M3.
3. All three Discord bots (Main Agent, Assistant, Tutor) reply to
   @-mention on the home channel. During staged swap, verify assistant +
   tutor upstream bot logins from their gateway logs; the default bot's
   @-mention is operator-owned (its token is held by the live private
   gateway — Step 2b note).
4. `library_search` callable from inside hermes (plugin tool or MCP tool)
   and returns citations for a known repo symbol. Native plugin shape:
   `hermes plugins list` shows the noahlw plugin; the gateway log shows the
   6 tools registered; invoke `hermes.indexer.tools.library_search` directly
   for deterministic citation evidence.
5. Honcho memory lands in the self-hosted instance — a prior chat fact is
   retrievable (`honcho_search` tool / `hermes honcho ...` / a query of the
   honcho-api Postgres DB).
6. Digest / scheduled job registered (`hermes cron list`) and its script
   invocable (run the digest script directly; the fire time may be
   unreachable in the verification window).
7. `ss -ltn` shows no public listeners — only 127.0.0.1 and Tailscale
   addresses (ssh/`rpcbind` on 0.0.0.0 are pre-existing).

Only when all 7 pass, proceed to Step 5.

## Step 5 — Decommission the private stack (this VM only)

1. Back up the gateway DB: `pg_dump` of the `hermes` database (see
   `scripts/vm/backup_postgres_drive.sh` for the existing backup pattern;
   rclone/age steps are operator-owned — a plain `pg_dump` to a local file is
   the minimum).
2. `systemctl disable --now hermes-gateway` and the private cron scheduler.
3. Drop the gateway DB **only with operator approval** (destructive op).
4. Archive the private per-persona HOME dirs now that nothing reads them:
   `mv ~/.hermes/profiles ~/.hermes/profiles.private-2026-08-05` (upstream
   owns `~/.hermes/profiles/` for `hermes profile create`).
5. Keep: honcho-api, honcho-deriver, ollama, codebase index, indexer webhook,
   indexer MCP, systemd timers.

---

# Maintaining the extension layer

- Upstream docs to read before touching the plugin: `website/docs/developer-guide/plugins/index.md` (plugin API: `register(ctx)`, `ctx.register_tool/hook/cli_command/command`, `ctx.dispatch_tool`), `website/docs/user-guide/features/plugins.md` (discovery), `website/docs/user-guide/features/hooks.md` (hook list), `website/docs/user-guide/features/mcp.md` (MCP config), `website/docs/user-guide/profiles.md` + `multi-profile-gateways.md`, `website/docs/user-guide/configuring-models.md`, `website/docs/user-guide/features/honcho.md`.
- Upstream ships its own huge `AGENTS.md` at the repo root — read it for deep extension work.
- The private runtime's 411-test suite lives in `archive/tests/` as a behavioral reference; the plugin's correctness is validated by the 7-check gate on the VM (Q8 — no in-repo test suite was ported).
- Standalone plugin repos are upstream's official third-party distribution model — this repo follows it.
- Hook contract drift: upstream pins nothing for us; re-check `pre_gateway_dispatch` action-dict semantics against the installed version whenever `hermes update` bumps major/minor.

## Working conventions

- One git worktree per ticket; never implement directly on the checkout the operator is using.
- PRs close their ticket (`Closes #N`); the reviewer gate applies to install-contract/ADR/PR changes.
- Keep edits scoped; archived code is reference-only — port, don't edit in place.