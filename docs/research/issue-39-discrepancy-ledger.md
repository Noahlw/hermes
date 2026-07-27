# Issue #39 Discrepancy Ledger

> Verdict table comparing live VM facts vs every concrete claim in `docs/use-case-specification.md` (the "weak-model" deliverable for #39).
>
> **Re-audit date:** 2026-07-26 (Oracle VM `100.79.87.93`, read-only SSH via `~/.ssh/hermes-vm-leaked`).
> **Source doc:** [`docs/use-case-specification.md`](../use-case-specification.md).
> **Method:** 8 parallel SSH audits (A1 inventory, A2 config, A3 sessions, A4 memory, A5 cron, A6 personas, A7 runtime, A8 capability gap).
>
> **Verdict codes:**
> - `CONFIRMED` — claim matches live VM.
> - `FALSE` — claim is contradicted by live VM.
> - `NOT_PRESENT_YET` — spec asserts something that does not exist on the VM and must be built.
> - `CONTRADICTS_NONNEGOTIABLE` — claim is true but breaks one of the §8 non-negotiables.
> - `QUALIFIED` — claim is mostly correct with a caveat.

---

## Critical Findings Summary

1. **All 8 spec'd MCP tool names are `NOT_PRESENT_YET`.** Zero hits anywhere in source, config, CLI subcommands, or AGENTS.md. Hermes v0.15.1 *does* ship MCP machinery (`mcp_serve.py`, `tools/registry.py`, ~20 files with `@mcp.tool`/`app.tool`) and 49 CLI subcommands including `mcp tools kanban memory skills` — none of them match the spec's names.
2. **Hermes is NOT in Docker.** It's a host Python venv supervised by `hermes-gateway.service` (49-day uptime). The `/usr/local/bin/hermes` wrapper is a MEM0/worktree env shim, not a docker exec. The probe-summary narrative was wrong.
3. **`research/`, `worktrees/`, and `cron/vm_health.sh`** — `research/` and `worktrees/` literally absent from `/home/ubuntu/.hermes/`. `vm_health.sh` exists at `scripts/vm_health.sh` (different path).
4. **Tailscale listener surface is much wider than spec implies.** Open WebUI (3000), nginx (80/443), geo-auditor (3080/3081), AgentMemory (3111/3112/49134), Hermes gateway (8642), rpcbind UDP are all reachable via Tailscale — the "zero public exposure" non-negotiable is at risk for these, not just SSH + tailscaled.
5. **`MiniMax-M3` is the default**, but the spec's "MiniMax-only execution" claim is `FALSE` — delegation uses `deepseek/deepseek-v4-flash` through `openrouter` with fallback chain `['openrouter','openai-codex','deepseek']`, which the spec itself acknowledges in §6.2 and again contradicts in §8 (Non-Negotiables).
6. **Telegram vs Discord (updated 2026-07-26):** `GATEWAY_ALLOW_ALL_USERS=true` and Telegram `gncsbot` still exist on the VM, but **D-DISC-1 = A** removes Telegram from V1. Discord home channel + `DISCORD_ALLOWED_USERS` is the sole end-user chat surface. Legacy Telegram keys remain as observed facts only.
7. **`SOUL.md` is effectively empty** (only a commented example block, no live persona content). **No `default` persona profile directory exists.** Profiles are role/task containers (`coder`, `council`, `research`, `runner`), not personality personas. The Q8/Q8.1 6-persona design is a target, not a current capability.
8. **Weekly-workspace-cleanup cron is broken** with a **401 auth failure on API key `****f14d`** — needs triage before cron digest can work.
9. **`kanban.db` is empty** (all 7 tables zero rows) and the table is called `tasks`, not `tickets`.
10. **`state.db`** does *not* have `profiles` or `skills` tables — the "4 active profiles / 33 skill categories" claim is filesystem evidence only.

---

## Claim Ledger

### §6.1 Bounded Directory Inventory Counts

| Claim ID | Spec claim | Reality (VM) | Verdict |
|---|---|---|---|
| DIR-1 | 34 top-level files under `/home/ubuntu/.hermes/` | 34 files (live `find -maxdepth 1` confirms) | `CONFIRMED` |
| DIR-2 | 26 subdirectories under `/home/ubuntu/.hermes/` | 26 directories | `CONFIRMED` |
| DIR-3 | `cron/` contains 10,034 files | 10,246 files (+212) | `QUALIFIED` |
| DIR-4 | `hermes-agent/` contains 55,850 files | 55,786 (−64) | `QUALIFIED` |
| DIR-5 | `node/` contains 29,037 files | 29,013 (−24) | `QUALIFIED` |
| DIR-6 | `profiles/` contains 1,313 files | 1,313 | `CONFIRMED` |
| DIR-7 | `sessions/` contains 3,878 files | 3,878 | `CONFIRMED` |
| DIR-8 | `skills/` contains 612 files | 612 | `CONFIRMED` |
| DIR-9 | `/home/ubuntu/.hermes/worktrees/` exists | Path is **absent** | `FALSE` |
| DIR-10 | `/home/ubuntu/.hermes/research/` exists | Path is **absent** | `FALSE` |
| DIR-11 | `/home/ubuntu/.hermes/logs/agent.log` exists | Path exists (2.7 MB, modified 2026-07-25 18:11) | `CONFIRMED` |
| DIR-12 | `/home/ubuntu/.hermes/cron.log` exists | **Absent** — cron output stored at `cron/output/<job-id>/<timestamp>.md` (10,245 files) | `FALSE` |

### §6.2 Configuration & Gateway

| Claim ID | Spec claim | Reality (VM) | Verdict |
|---|---|---|---|
| CFG-1 | `model.default: MiniMax-M3` | Verified | `CONFIRMED` |
| CFG-2 | `MiniMax-M3` is the *only* model in use | Delegation runs `deepseek/deepseek-v4-flash` via `openrouter`; fallback chain openrouter/openai-codex/deepseek active | `CONTRADICTS_NONNEGOTIABLE` |
| CFG-3 | `delegation.provider: openrouter` | Verified | `CONFIRMED` |
| CFG-4 | fallback chain `['openrouter','openai-codex','deepseek']` | Verified, same order | `CONFIRMED` |
| CFG-5 | `channel_directory.json` lists bot `gncsbot` ID `6396579368` | Verified exactly | `CONFIRMED` |
| CFG-6 | `.env` currently has `GATEWAY_ALLOW_ALL_USERS=true` | Verified, literally `true` | `CONFIRMED` |
| CFG-7 | `.env` contains `TELEGRAM_ALLOWED_USER_ID` | **Absent** — the allowlist gate is not in `.env` | `NOT_PRESENT_YET` |
| CFG-8 | All 1:1 Telegram peers are rejected if not authorized | Current state: `GATEWAY_ALLOW_ALL_USERS=true` and no allowlist key — every peer accepted | `CONTRADICTS_NONNEGOTIABLE` |
| CFG-9 | VM only exposes SSH + tailscaled on Tailscale | Open WebUI (3000), nginx (80/443), geo-auditor (3080/3081), AgentMemory (3111/3112/49134), Hermes gateway (8642), rpcbind UDP all reachable over Tailscale | `CONTRADICTS_NONNEGOTIABLE` |

### §6.3 Database & Memory

| Claim ID | Spec claim | Reality (VM) | Verdict |
|---|---|---|---|
| DB-1 | `state.db` has 7,060 messages | 7,060 rows in `messages` | `CONFIRMED` |
| DB-2 | `state.db` covers 2,177 sessions | 2,177 rows in `sessions`; only 2,174 distinct message-linked session IDs | `QUALIFIED` |
| DB-3 | `state.db` is a SQLite database | Valid unencrypted SQLite 3, ~99 MB | `CONFIRMED` |
| DB-4 | Session `20260515_140232_e5cae2` exists w/ Msgs 879/889/893/905 | Exists; 64 messages; all four IDs verified with tutor-content excerpts | `CONFIRMED` |
| DB-5 | Session `20260515_175823_864500` exists w/ Msg 960 | Exists; 66 messages; Msg 960 verified | `CONFIRMED` |
| DB-6 | Session `20260516_004506_fb9729` exists w/ Msg 1035 | Exists; 49 messages; Msg 1035 verified | `CONFIRMED` |
| DB-7 | `state.db` shows 4 active profiles / 33 skill categories | No `profiles` or `skills` tables in `state.db`; filesystem shows 4 profile dirs (`coder`/`council`/`research`/`runner`) and 33 visible skill categories (after excluding `.archive`, `.curator_backups`, `.hub`) | `QUALIFIED` |
| DB-8 | `memories/MEMORY.md` & `USER.md` have travel/hair/Nagasaki facts + `agentmemory` v0.9.24 reference | Both files exist; `agentmemory` confirmed at `127.0.0.1:8642` /health `{"platform":"hermes-agent"}` | `CONFIRMED` |

### §4 Persona Roster vs Reality

| Claim ID | Spec claim | Reality (VM) | Verdict |
|---|---|---|---|
| PERS-1 | `SOUL.md` defines a `default` persona | `SOUL.md` body is effectively empty (only a commented example block) | `FALSE` |
| PERS-2 | Existing persona profiles include `default` and `coder` | Only `coder`, `council`, `research`, `runner` exist; **no `default`** | `FALSE` |
| PERS-3 | 6 personas (`Main Agent`, `Librarian`, `Developer`, `Researcher`, `Assistant`, `Tutor`) are existing operational identities | Persona roster is a **target contract**, not currently implemented; they exist only as Q1–Q12 HITL decisions | `NOT_PRESENT_YET` |
| PERS-4 | Persona profiles are isolated working memory with shared codebase knowledge layer | Memory today is shared qdrant_mem0 + mem0 + agentmemory + honcho with a thin `mem0.json` (only `user_id`/`agent_id`/`rerank`); no persona/task/visibility scope | `NOT_PRESENT_YET` |

### §5 MCP Tool Surface (8 tools)

| Claim ID | Tool | Reality (VM) | Verdict |
|---|---|---|---|
| TOOL-1 | `library_search(query, repos?, revision?, limit?)` | 0 hits in source, config, AGENTS.md, CLI | `NOT_PRESENT_YET` |
| TOOL-2 | `generate_plan(task_description, repo, base_ref?)` | 0 hits | `NOT_PRESENT_YET` |
| TOOL-3 | `execute_plan(plan_id, repo, confirm_execute)` | 0 hits | `NOT_PRESENT_YET` |
| TOOL-4 | `push_plan_pr(plan_id, repo, branch, title, body, confirm_push)` | 0 hits; PR creation is a shell-level step | `NOT_PRESENT_YET` |
| TOOL-5 | `conduct_research(topic, sources?, sensitivity?)` | 0 hits; `skills/research/` exists but is a packaged skill, not an MCP tool | `NOT_PRESENT_YET` |
| TOOL-6 | `conduct_tutoring(subject, repo_url?, language?, detail_level?)` | 0 hits | `NOT_PRESENT_YET` |
| TOOL-7 | `manage_tasks(action, task_id?, content?, confirm_delete?)` | 0 hits; `hermes kanban` is the closest CLI but is not named `manage_tasks` | `NOT_PRESENT_YET` |
| TOOL-8 | `agent_query(persona?, prompt)` | 0 hits | `NOT_PRESENT_YET` |
| TOOL-9 | Hermes exposes MCP tool surface today | True *infrastructure*: `mcp_serve.py`, `tools/registry.py`, `tools/mcp_tool.py`, `tools/delegate_tool.py`, `tests/tools/test_mcp_*.py` all present; 49 CLI subcommands incl. `mcp`/`tools`/`kanban`/`memory`/`skills` | `QUALIFIED` — tooling is present but names differ |

### §1 Use Cases — file/path contracts

| Claim ID | Spec claim | Reality (VM) | Verdict |
|---|---|---|---|
| UC-1 | `Researcher` writes to `/home/ubuntu/.hermes/research/<slug>.md` | `/home/ubuntu/.hermes/research/` **does not exist** | `NOT_PRESENT_YET` |
| UC-2 | `Developer` mutates worktrees under `/home/ubuntu/.hermes/worktrees/<repo>/<task_id>/` | `/home/ubuntu/.hermes/worktrees/` **does not exist** | `NOT_PRESENT_YET` |
| UC-3 | `Main Agent` cron invokes `vm-health-check` → `vm_health.sh` | `vm_health.sh` exists at `scripts/vm_health.sh` (not `cron/`); `vm-health-check` is healthy (56 runs) | `QUALIFIED` |
| UC-4 | `Main Agent` cron `weekly-workspace-cleanup` is wired | Job exists but **broken with 401 auth failure on key `****f14d`** | `FALSE` |
| UC-5 | Telegram `gncsbot` enforces 1:1 sender match | Config allows all and no allowlist key — every peer accepted | `CONTRADICTS_NONNEGOTIABLE` |
| UC-6 | Tutor sessions are persistent and recallable | All 3 named sessions + 6 IDs verified with real Cantonese/RAG content | `CONFIRMED` |

### §6.1 — runtime topology

| Claim ID | Spec claim | Reality (VM) | Verdict |
|---|---|---|---|
| RUN-1 | Hermes is hosted via Docker Compose | Hermes is a host Python venv at `/home/ubuntu/.hermes/hermes-agent/venv`, supervised by systemd-user `hermes-gateway.service` (49-day uptime) | `FALSE` |
| RUN-2 | `/usr/local/bin/hermes` is a Docker exec shim | Wrapper is a 19-line bash shim that sets `MEM0_DEFAULT_APP_ID` + executes the venv | `FALSE` |
| RUN-3 | `hermes-personal:latest` is the runtime image | Image exists but is **orphaned** (2.29 GB build, no containers using it) | `QUALIFIED` |
| RUN-4 | Open WebUI on Tailscale `100.79.87.93:3000` | Reachable: HTTP 200 | `CONFIRMED` |
| RUN-5 | Install is current | 182 commits behind upstream; `hermes update` overdue | `QUALIFIED` |
| RUN-6 | Dashboard is up | Not running (no listener on 9119) | `FALSE` |

### §6.2 — gateway memory stack

| Claim ID | Spec claim | Reality (VM) | Verdict |
|---|---|---|---|
| MEM-1 | Qdrant runs on `127.0.0.1:6333` | Verified, 4 collections: `mem0`, `mem0_nomic`, `mem0migrations`, `terraforming` | `CONFIRMED` |
| MEM-2 | mem0 is configured | `~/.hermes/mem0.json` exists but is thin. **Enrichment / whether to keep mem0 deferred to #41** | `QUALIFIED` (observed; cleanup ticket #41) |
| MEM-3 | agentmemory systemd unit on `0.0.0.0:8642` | Verified running. **D-MEM-3: out of V1 — uninstall entirely** | `CONFIRMED` (slated for removal) |
| MEM-4 | Honcho via docker compose | Verified. **Fate deferred to #41** | `CONFIRMED` (observed) |
| MEM-5 | neo4j on 7474/7687 | Verified. **Fate deferred to #41** | `CONFIRMED` (observed) |
| MEM-6 | ollama on `127.0.0.1:11434` | Verified; 4 models. **Not a memory service** — local LLM/embedding inference only; remove from memory-stack framing | `QUALIFIED` (misclassified in prior draft) |

### §2.4 Cron Spec Names

| Claim ID | Spec claim | Reality (VM) | Verdict |
|---|---|---|---|
| CRON-1 | `vm-health-check` is a defined cron job | Verified in `cron/jobs.json`; healthy | `CONFIRMED` |
| CRON-2 | `weekly-workspace-cleanup` is a defined cron job | Verified but **currently failing 401** on `****f14d` | `QUALIFIED` |
| CRON-3 | `ollama-keep-alive` is a defined cron job | Verified | `CONFIRMED` |
| CRON-4 | Hermes cron is system cron | In-process only (JSON-driven); no `crontab`, no systemd timers; `cron` and `crontab` CLIs not installed on the VM | `QUALIFIED` |
| CRON-5 | kanban.db is a subagent delegation store | `kanban.db` exists with 7 tables (`tasks`, `task_links`, `task_comments`, `task_events`, `task_runs`, `kanban_notify_subs`, `sqlite_sequence`); **all tables empty**; primary table is `tasks` not `tickets` | `QUALIFIED` |

---

## Decision Items Still Pending (Grill Round)

After the rewrite, the parent will grill these one at a time:

1. **D-NN-1: MiniMax-only enforcement scope.** **DECIDED: A** — Keep MiniMax-only non-negotiable; harden `config.yaml` delegation routes before #39 can close.
2. **D-GW-1: Telegram 1:1 enforcement.** **SUPERSEDED by D-DISC-1** — Telegram is out of V1; do not spend grill cycles on `TELEGRAM_ALLOWED_USER_ID`.
3. **D-DISC-1: Discord as sole V1 chat surface.** **DECIDED: A** — Assistant listens only on `DISCORD_HOME_CHANNEL`; senders must be in `DISCORD_ALLOWED_USERS`. Telegram fully out of V1. Follow-through: disable Telegram gateway paths for V1 and verify Discord allowlist enforcement.
4. **D-EXP-1: Tailscale listener surface.** **DECIDED: A** — Document accepted Tailscale services (SSH, tailscaled, Hermes gateway, Open WebUI, AgentMemory). Leftover ports (nginx, geo-auditor, rpcbind) are cleanup debt, not #39 blockers. Non-negotiable = no internet-public exposure.
5. **D-RUN-1: Hermes runtime topology.** **DECIDED: A** — Host venv + `hermes-gateway.service` is canonical; Docker-Compose Hermes narrative retired. §6 already reflects this.
6. **D-CAP-1: MCP tool names.** **DECIDED: A** — Keep the §5 names as the V1 target surface; register them on the existing Hermes MCP server. Live CLIs (`hermes kanban`/`hermes memory`) are transitional only.
7. **D-MEM-3: AgentMemory removal.** **DECIDED** — AgentMemory (`iii`) MCP is out of V1 and must be **uninstalled entirely** before #39 closes: stop + disable `agentmemory.service`, remove `~/.local/bin/iii` and `~/.agentmemory/`, drop ports `3111`/`3112`/`49134` from accepted Tailscale services, remove from §6.5 memory stack, and unregister its MCP toolset.
8. **D-CRON-1: 401 on weekly-workspace-cleanup.** **KEEP ON #39 (blocking for §1.4)** — triage auth failure (`****f14d`) before calling cron-digest “working.”
9. **D-CRON-2: kanban.db empty.** **NON-BLOCKING** — document as observed; confirm cold-start vs outage later; does not block #39 close.
10. **MEM-2 / memory-stack consolidation.** **DEFERRED to #41** — #39 does not pick among Qdrant/mem0/Honcho/neo4j. Research ticket #41 decides if the current stack is good enough or a better memory service exists. Only agentmemory has a #39 removal decision (D-MEM-3). Ollama is inference, not memory.

---

## Source Trail

| Agent | Domain | Verdict distribution |
|---|---|---|
| A1 Inventory | `/home/ubuntu/.hermes/` layout | 6 CONFIRMED / 3 QUALIFIED / 3 FALSE (paths) |
| A2 Config | provider / gateway / channels / `.env` | 4 CONFIRMED / 3 NOT_PRESENT_YET / 3 CONTRADICTS_NONNEGOTIABLE / 0 FALSE |
| A3 Sessions | `state.db` claims | 6 CONFIRMED / 2 QUALIFIED / 0 FALSE |
| A4 Memory | qdrant/mem0/agentmemory/honcho/neo4j/ollama | 5 CONFIRMED / 1 QUALIFIED |
| A5 Cron/Ops | `cron/`, `vm_health.sh`, kanban, agent.log | 4 CONFIRMED / 4 QUALIFIED / 0 FALSE (note: `cron.log` and `cron/vm_health.sh` corrections are documented) |
| A6 Personas | `profiles/`, `SOUL.md`, memories | 3 CONFIRMED / 2 FALSE (SOUL empty, no `default` persona) / 2 NOT_PRESENT_YET |
| A7 Runtime | runtime topology, dashboard, wrapper | 1 CONFIRMED / 3 QUALIFIED / 3 FALSE |
| A8 Capability Gap | 8 MCP tools vs code | 0 CONFIRMED / 1 QUALIFIED / 8 NOT_PRESENT_YET |

---

## Out of scope for this ledger

- Decisions on non-negotiable widening vs enforcement
- Designing the V1 implementation tickets
- Grilling #40–#44
- Harvesting secret values from `.env` (only key names + truthy/falsy collected)
- Replacing the leaked RSA SSH key (separate ticket #36)
