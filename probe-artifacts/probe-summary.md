# Hermes VM Probe Summary

> Snapshot of `/home/ubuntu/.hermes/`-and-surroundings on `129.150.37.112` taken 2026-07-23 via SSH (using the leaked RSA key — risk explicitly accepted).
> Artifacts: `probe-a..d.txt` + `hermes-setup-plan.md` in this directory.

## Identity

| | |
|---|---|
| Host | `instance-20260511-1727` |
| OS | Ubuntu 24.04.4 LTS (Noble Numbat) |
| Arch | aarch64 (Oracle ARM / Ampere) |
| Resources | 4 CPU · 23 GiB RAM · 193 GB disk (46% used, 105 GB free) |
| Tailscale IP | `100.79.87.93` |
| Userland | `ubuntu` (uid 1000) |

## What `hermes-agent` is — already installed, mature

- **Version**: `Hermes Agent v0.15.1` (release `2026.5.29`)
- **Project dir**: `/home/ubuntu/.hermes/hermes-agent/` (full Nous Research source tree, including `AGENTS.md` 53 KB, all `RELEASE_v0.x.x.md` notes from v0.2 → v0.15.1)
- **Runtime**: Docker Compose (`hermes-agent` + `hermes-dashboard` containers, custom `hermes-personal.Dockerfile`)
- **Thin wrapper**: `/usr/local/bin/hermes` is a shim that delegates to the Docker container
- **Python on host**: 3.12.3; **Python in container**: 3.11.15
- **Run state**: `hermes` (container) running; `agentmemory.service` (systemd) running; tailscaled running

## What `/home/ubuntu/.hermes/` already has

```
/home/ubuntu/.hermes/
├── SOUL.md                    ← persona document (empty body, ready to fill)
├── config.yaml (13 KB)        ← main config; 4 .bak files of v0.x history
├── .env (23 KB, mode 600)     ← secrets — Hermes reads this
├── .hermes_history (35 KB)    ← session memory log
├── auth/ + auth.json          ← authentication state
├── bin/                       ← custom CLI scripts
├── cache/                     ← model + dev cache
├── checkpoints/               ← checkpoint restoration state
├── cron/                      ← Hermes cron jobs live here (no /etc/cron.d user crons)
├── gateway/ + gateway*.{lock,pid,state}   ← gateway run state
├── hermes-agent/              ← project source (separate from data dir)
├── hooks/, image_cache/, images/, logs/   ← subdirs
├── kanban.db                  ← Kanban subagent delegation store
├── mem0.json, honcho.json     ← memory backend config
├── memories/                  ← persistent memory
├── sessions/                  ← 60+ session_cron_*.json + request_dump_*.json files
└── ... (and more)
```

## Memory stack — already deployed (T-008 effectively DONE)

| Service | How | Status |
|---|---|---|
| **qdrant_mem0** | Docker container, image `qdrant/qdrant:latest` | Up 6 weeks; binding `127.0.0.1:6333-6334` |
| **mem0** | `/home/ubuntu/.mem0/`, `/home/ubuntu/mem0-local/`, `~/.hermes/mem0.json` | Configured; backed by Qdrant |
| **agentmemory** | `https://github.com/rohitg00/agentmemory`; systemd unit `agentmemory.service`; binary `/home/ubuntu/.local/bin/iii --config /home/ubuntu/.agentmemory/iii-config.yaml` | Running on port **8642** (python pid 1110911) |
| **honcho-self-hosted** | Docker Compose stack (postgres + redis + api + deriver + database); `~/.hermes/honcho.json` peer `hermes` observing `ubuntu` | Up 7 weeks |
| **neo4j** | Docker container; ports 7474/7687 | Up 6 weeks |
| **ollama** | Local LLM server (systemd) | Up; binding `127.0.0.1:11434` |

## Tailscale status

| Node | IP | OS | Online |
|---|---|---|---|
| `instance-20260511-1727` (this VM) | 100.79.87.93 | linux | **online** |
| `noahpc` | 100.92.48.121 | windows | offline 11d |
| `noahs-macbook-air` (this Mac) | 100.104.102.94 | macOS | **offline 20h** (needs `tailscale up` on Mac) |
| `node` | 100.127.177.18 | macOS | offline 31d |

DERP latency: Singapore (1.9 ms — DERP nearest), Hong Kong (34.2 ms), Bengaluru (37.9 ms), Tokyo (66.8 ms).

## Skills available on this Hermes install

`apple/`, `autonomous-ai-agents/`, `creative/`, `data-science/`, `devops/`, `diagramming/`, `dogfood/`, `domain/`, `email/` — and probably more skills live under each.

## Plugins enabled

`browser/`, `context_engine/`, `dashboard_auth/`, `disk-cleanup/`, `example-dashboard/`, `google_meet/`, `hermes-achievements/`.

The local-mac Hermes config (at `~/.hermes/config.yaml` on this Mac, 38 bytes) is **a stub** — `plugins.enabled: [orca-status]` only. The real work is on the VM.

## Other services running (and what they suggest)

- **`open-webui`** on `100.79.87.93:3000` and `127.0.0.1:3000` — chat UI; the user has been hosting an Open WebUI in addition to Hermes
- **`geo_auditor_test`** stack on `0.0.0.0:3080/3081` — appears to be an evaluation harness for a project, not part of the Hermes stack
- **nginx** on 80/443 — likely reverse-proxying Open WebUI / Honcho / Agentmemory
- **`agentmemory-iii-init-1`** Exited 0 — looks like a one-shot migration container

## What's in the user's setup plan (`hermes-setup-plan.md`, 205 lines)

A 5-step work-in-progress migration plan:

1. **Subagent fallback chain**: `openrouter/deepseek-v4-flash` → `openai-codex/Codex 5.2` (GitHub Copilot OAuth) → `deepseek/deepseek-v4-flash`
2. **Token optimization**: tighten `compression.threshold` to 65%, `target_ratio` to 15%, cap Honcho context budget at 4000 tokens, schedule dialectic every 3 turns instead of every turn
3. **Config polish**: `hermes doctor --fix` for v23 → v24, enable checkpoints, add GITHUB_TOKEN
4. **VM maintenance cron**: daily 06:00 UTC health check; weekly 03:00 Sunday workspace cleanup
5. **Coder profile**: bring `coder` profile (using `gemini-3.1-pro-preview`, `hermes-personal:latest`) up to current standards — config migration, Honcho setup, memory enable, toolset list, env sync

The plan is **incomplete** — Steps 1-5 haven't been marked done.

## What's NOT on the VM (the chart's missing pieces)

- ❌ **Wiki + librarian MCP** — no code-index-mcp / Serena / custom tree-sitter server
- ❌ **Persona YAMLs** — `~/.hermes/hermes-agent/personalities/` doesn't exist; `SOUL.md` is empty
- ❌ **Token-cost ledger** — no per-persona/per-task burn sheet
- ❌ **Heartbeat / `hermes-status`** — no formal observability
- ❌ **Monthly auto-research** — no cron or script for monthly upgrade recommendations
- ❌ **Public-facing MCP endpoints** — flagged as out-of-scope per D-005 (good)

## What this implies for the chart

The chart's premise was wrong in five places:

1. Path: chart assumed `/opt/hermes/`; reality is `/home/ubuntu/.hermes/` with `~` → `/opt/data` inside the container.
2. Memory backend was the headline decision; it's **already settled** (Qdrant + mem0 + agentmemory + Honcho triple-stack).
3. The user's existing config has the DEFAULT profile + a CODER profile; the chart's "persona menu" framing is correct in spirit but doesn't yet reflect `coder` as a real persona.
4. Tailscale is already running on the VM; the chart's T-018 is effectively done at VM-side. The other-PC tailscale clients are stale (offline 11d, 20h, 31d).
5. The `hermes-setup-plan.md` is an in-flight plan; the chart should be the **outer** wayfinder map, with the setup-plan steps living as a sub-section.

## Decision: what redraft means

Per user's "Full restart" preference:

- Close map #1.
- Open new map `#N`.
- Re-ticket every gap based on probe truth, not the hypothetical.
- Carry D-001..D-014 as institutional memory into the new map's *Decisions so far*.
- Re-issue `Hermes/GRANDMAP.md` v2.

## Open questions for the redraft

1. **Re-read `hermes-setup-plan.md` content end-to-end** before deciding which steps become tickets — the user wrote 5 steps for a reason. (Probe-c has it; I can pull it. Already saved in this directory.)
2. **The user's choice of Qdrant + mem0 + agentmemory + Honcho simultaneously** — was this deliberate stacking or incremental accumulation? If intentional, document; if accidental, future tickets may consolidate.
3. **`coder` profile** — should it remain a separate persona (persona YAML = coder), or merge into a unified `agent` persona? Both are reasonable. Probe-side the codebase supports `~/.hermes/profiles/coder/` and `hermes --profile coder`.
4. **Tailscale client on this Mac** — needs `tailscale up` (offline 20h). Should I run that here, or is it user-driven?
5. **Token-cost tracking (T-023)** — the user has `kanban.db` and `mem0.json` + Honcho but no formal per-token ledger. Is the cost data already being captured somewhere we haven't looked?
