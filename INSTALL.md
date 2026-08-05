# Install — Hermes (official agent + this repo's extensions)

> **This repo is the installer playbook + extension layer for the official
> Hermes Agent** (NousResearch/hermes-agent). It does not ship a runtime.
> ADR 0007; old bespoke installers are archived under `archive/`.

**Coding agents: read [AGENTS.md](./AGENTS.md) and follow it step by step.**
It is the complete, executable runbook: install the official agent the
official way, configure MiniMax-M3 + profiles + memory + indexer MCP, apply
the extension layer, verify with the 7-check gate, then decommission the old
stack.

## TL;DR (humans)

1. **Install the official agent** on the VM:
   ```bash
   curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
   ```
   Installs to `~/.hermes/hermes-agent`, launcher `~/.local/bin/hermes`.
   Skip the interactive wizard on headless VMs — everything below is
   configured by file, then `hermes doctor` verifies.
2. **Configure** (`~/.hermes/config.yaml` + `~/.hermes/.env`):
   - MiniMax-M3 provider (only LLM, `providers.minimax` custom endpoint)
   - Profiles: default = Main Agent; `assistant`, `tutor` — each with its
     own Discord bot token (`~/.hermes/profiles/<name>/.env`)
   - Honcho memory → self-hosted API (`~/.hermes/honcho.json`,
     `hermes memory setup honcho`); Ollama embeddings stay local
   - Indexer MCP server (`mcp_servers.hermes-indexer`)
3. **Apply extensions**: `pip install -e` this repo into the upstream venv,
   drop the `~/.hermes/plugins/noahlw/` shim (contract gate), digest skill,
   quick commands, schedules.
4. **Verify** (all 7): `hermes doctor` clean · `hermes chat -q` answers via
   MiniMax · all three Discord bots reply · `library_search` works with
   citations · Honcho memory lands · digest fires · no public listeners.
5. **Decommission** the old private stack (backup DB → stop/disable
   `hermes-gateway` + private scheduler → drop DB with operator approval).

## Quick reference

| Thing | Command / path |
|---|---|
| Official install | `curl -fsSL https://hermes-agent.nousresearch.com/install.sh \| bash` |
| Runtime home | `~/.hermes/` (`config.yaml`, `.env`, `hermes-agent/`, `plugins/`, `skills/`, `honcho.json`) |
| CLI | `hermes` (TUI), `hermes chat -q`, `hermes setup`, `hermes model`, `hermes doctor`, `hermes gateway install/start/stop`, `hermes profile create`, `hermes memory setup honcho`, `hermes mcp`, `hermes config set/get`, `hermes update` |
| Profiles | `hermes -p <name> ...`; per-profile gateway service `hermes-gateway-<name>.service` |
| This repo's code | `hermes/personas/` (contracts), `hermes/hermes_agent_plugin/` (hook adapter), `hermes/indexer/`, `hermes/digest/`, `hermes/profiles/`, `setup/ollama/` + `setup/honcho/` (memory infra) |
| Archived | `archive/` — old private runtime (`hermes_agent/`, `tests/`, `cron/`, `setup/install.sh`, `setup/gateway.sh`, `setup/systemd/`) |

## Requirements

- Ubuntu 24.04 aarch64 (Oracle Cloud Ampere A1: 2 OCPU / 12 GB) — ARM is a
  solved constraint (upstream installer manages uv + Python 3.11).
- Tailscale for all cross-PC traffic; zero public exposure.
- Existing VM services that stay: honcho-api, honcho-deriver, ollama
  (127.0.0.1:11434), codebase index + indexer MCP, systemd timers.

## Troubleshooting

- `hermes` not found after install → `source ~/.bashrc` (launcher is
  `~/.local/bin/hermes`).
- Hook not firing → re-check the `pre_gateway_dispatch` contract against the
  installed upstream version (see AGENTS.md §Maintaining).
- Memory not landing → check `~/.hermes/honcho.json` `baseUrl` + honcho-api
  port, `hermes status`.
- Discord silent → token scope (`~/.hermes/profiles/<name>/.env`) and
  allowlist (`DISCORD_ALLOWED_USERS`) — never a public bind.