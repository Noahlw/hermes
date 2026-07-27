# Hermes V1 Use-Case Specification

> **Status (2026-07-26):** This document was rewritten to separate **observed VM facts** (§6, post-audit) from **V1 target contracts** (§1–5, §7–10). The 2026-07-24 "weak-model" draft conflated current capability with target state. The full per-claim verdict table is in [`docs/research/issue-39-discrepancy-ledger.md`](research/issue-39-discrepancy-ledger.md).
>
> Hermes V1 target on the user's Oracle VM at `/home/ubuntu/.hermes/`, exposed only through Tailscale as an MCP server, driven by MiniMax-M3.

---

## 1. Use Case Inventory (6 Core Workloads)

> **Reader note:** Each subsection below describes a **V1 target workload**. None of the persona assignments, workspace paths, or MCP tool names are guaranteed to exist on the VM today — see §6 for observed reality and §5 for "V1 target MCP surface" framing.

### 1.1 Knowledge Retrieval (Codebase Wiki)
- Multi-repo cross-cutting search across 20–100 GitHub repos.
- Response format: Synthesized Markdown summary with precise revision citations (`repo`, `revision`, `file`, `line_range`, `symbol`).
- **Assigned Persona (target):** `Librarian`.

### 1.2 Code Plan Implementation
- Two-stage execution model (`generate_plan` → caller review → `execute_plan`).
- Execution workspace (target): isolated Git worktree at `/home/ubuntu/.hermes/worktrees/<repo>/<task_id>/` under feature branch `hermes/plan-<task_id>`. Primary checkouts on the VM are never touched.
  - **CURRENT STATE:** `/home/ubuntu/.hermes/worktrees/` does not exist on disk today (ledger DIR-9).
- Local worktree mutation vs. remote PR delivery: local commits by `execute_plan` (requires `confirm_execute: true`). Remote delivery by `push_plan_pr` (requires `confirm_push: true`).
- **Assigned Persona (target):** `Developer`.

### 1.3 Technical Research Agent
- Markdown reports saved to `/home/ubuntu/.hermes/research/<slug>.md`.
  - **CURRENT STATE:** `/home/ubuntu/.hermes/research/` does not exist on disk today (ledger UC-1).
- Memory indexing: public technical facts enter shared memory; private notes/tasks tagged `sensitivity: "private"` restricted to persona-local memory.
- **Assigned Persona (target):** `Researcher`.

### 1.4 Background Cron & System Monitoring Digest
- VM health digests, re-indexing status, workspace cleanup.
- `clean_workspace` defaults to `dry_run: true`. Deletion requires explicit `confirm_delete: true`.
- **CURRENT STATE:** `vm-health-check` is healthy (56 runs, last OK 2026-07-25). `weekly-workspace-cleanup` is a defined job but **currently failing with a 401 auth error** on an API key prefix `****f14d` (ledger CRON-2) — must be triaged before §10's "Cron Digest" row is treated as working.
- **Assigned Persona (target):** `Main Agent`.

### 1.5 Personal Assistant / Discord Task Manager
- Instant note capture and daily task digests via Discord — **the only end-user chat channel in V1**.
- Authorization (target): messages only on `DISCORD_HOME_CHANNEL`; sender must be in `DISCORD_ALLOWED_USERS`. Unauthorized senders and off-channel messages are dropped; no persona invoked.
  - **CURRENT STATE:** `.env` already has truthy `DISCORD_BOT_TOKEN`, `DISCORD_HOME_CHANNEL`, and `DISCORD_ALLOWED_USERS` (ledger A2). Telegram bot `gncsbot` / `TELEGRAM_BOT_TOKEN` still exist on the VM but are **out of V1** (D-DISC-1 = A).
- **Assigned Persona (target):** `Assistant`.

### 1.6 Academic Tutor & Exam / Internship Preparation
- **CURRENT EVIDENCE (confirmed in §6):** `state.db` session `20260515_140232_e5cae2` (Msgs 879, 889, 893, 905 — internship at Hypthon HK, LangGraph/RAG course walkthrough), session `20260515_175823_864500` (Msg 960 — Cantonese system prompt with English code identifiers), session `20260516_004506_fb9729` (Msg 1035 — request for university-tutor deep-dive depth).
- **Tutor Contract (target):**
  - Default `detail_level`: `"deep_dive"`.
  - Default `language`: `"cantonese_english_terms"`.
  - **Zero Summarization Rule:** when `detail_level: "deep_dive"`, deliver complete step-by-step code breakdowns without "refer to the docs."
- **Assigned Persona (target):** `Tutor`.

---

## 2. Representative Query / Command Patterns (V1 Target)

> **Reader note:** Each pattern is a V1 *contract*. None of these tool names exist on the VM today — see §5 for "Proposed MCP surface" framing and §6 ledger rows TOOL-1..8.

### 2.1 Knowledge Retrieval
- `library_search(query="how is auth handled across the api repos", repos=["api-core","api-gateway"], revision="main", limit=5)`
- `library_search(query="vector index error in faiss", limit=3)` (global cross-repo)

### 2.2 Code Plan Implementation
- `generate_plan(task_description="add /healthz endpoint to api-core", repo="api-core", base_ref="main")`
- `execute_plan(plan_id="plan_abc123", repo="api-core", confirm_execute=true)`
- `push_plan_pr(plan_id="plan_abc123", repo="api-core", branch="hermes/plan-abc123", title="Add /healthz", body="…", confirm_push=true)`

### 2.3 Technical Research
- `conduct_research(topic="embedding model choices for code retrieval", sources=["docs.repo-X","blog.Y"], sensitivity="public")` → writes `/home/ubuntu/.hermes/research/<slug>.md`.
- `conduct_research(topic="personal journal entry", sensitivity="private")` → restricted to Assistant-isolated memory.

### 2.4 Background Cron / Monitoring
- `vm-health-check` at `0 6 * * *` invokes `vm_health.sh`.
- `weekly-workspace-cleanup` at `0 3 * * 0` calls `clean_workspace(dry_run=true)` then (after review) `clean_workspace(confirm_delete=true)`. **Today: failing 401 — see ledger CRON-2.**
- `library_search(query="current VM health", limit=1)` from `Main Agent` consolidates cron results into a single digest.

### 2.5 Personal Assistant / Discord
- Inbound (authorized): message in `DISCORD_HOME_CHANNEL` from a user in `DISCORD_ALLOWED_USERS` → `manage_tasks(action="add", content="<msg>")`.
- Inbound (unauthorized / wrong channel / Telegram): dropped silently; no persona invoked.
- Outbound: `manage_tasks(action="list")` returns a concise task list rendered as a Discord reply in the home channel.

### 2.6 Academic Tutor
- `conduct_tutoring(subject="agentic RAG node logic", repo_url="https://github.com/emarco177/langgraph-course", language="cantonese_english_terms", detail_level="deep_dive")` → full step-by-step breakdown.
- `library_search(query="vector store retriever node impl")` (when the tutor needs a code anchor).

---

## 3. User vs Operator Boundary (V1 Target)

| Surface | Audience | Auth | Transport | Failure / Quarantine |
|---|---|---|---|---|
| Discord home channel | End user | `DISCORD_ALLOWED_USERS` + `DISCORD_HOME_CHANNEL` | Discord gateway → Hermes | Silent reject off-channel or off-allowlist; no other persona invoked |
| Personal notes & tasks (`Assistant`) | End user | Same as above | Discord → `manage_tasks` | Unauthorized messages dropped before any MCP call |
| Cron / VM health digests (`Main Agent`) | Operator | Local filesystem only (no MCP) | `cron/jobs.json` → `vm_health.sh` | Cron failure logged to `logs/agent.log`; no Discord broadcast |
| Code-plan execution (`Developer`) | Operator (via MCP client) | MCP over Tailscale | `execute_plan(confirm_execute=true)` | Without flag: returns `OUT_OF_SCOPE` |
| Research report writes (`Researcher`) | Operator (via MCP client) | MCP over Tailscale | `conduct_research` | Writes to `research/<slug>.md`; private tagged writes never enter shared memory |
| Tutor sessions (`Tutor`) | End user | MCP over Tailscale | `conduct_tutoring` | Deep-dive mode never returns "refer to the docs" |

---

## 4. V1 Persona Roster Contracts (Five Fixed Personas)

> **Reader note:** This section is the binding V1 roster contract from ADR 0003 and supersedes the older six-persona draft. See `docs/adr/0003-v1-persona-roster-and-contracts.md`.

Hermes V1 ships five fixed personas: `Main Agent`, `Librarian`, `Researcher`, `Assistant`, and `Tutor`. `Developer` is explicitly out of V1 while the coding-agent MCP remains information-only (ADR 0001).

Persona selection is transport-specific:
- **Discord:** @-mentioned bot identity selects persona (`Assistant`, `Tutor`, `Main Agent`).
- **MCP:** callers stay persona-agnostic; tool name maps to Librarian/Researcher jobs through one persona contract gate.
- **Cron/Ops:** run as `Main Agent` without Discord.

### 4.1 `Main Agent`
- **Purpose:** Ops + escalation persona and Discord super-set escape hatch (`Assistant ∪ Tutor ∪ ops`).
- **Allowed Actions:** `manage_tasks`, tutoring requests, ops/health/digest requests, and internal Librarian/Researcher jobs.
- **Authority Limits:** Does not narrate coding-agent MCP tool responses; no silent cross-bot handoff.
- **Memory Scope:** Dedicated Main Agent working-memory peer only.
- **Response Contract:** Markdown; concise for routine ops unless deeper detail is requested.
- **Acceptance Scenario:** Cron digest runs without Discord; `@Main Agent` can complete Assistant and Tutor workloads.

### 4.2 `Librarian` (job-backed)
- **Purpose:** Codebase information authority for retrieval and citation workflows.
- **Allowed Jobs:** `library_search`, `session_brief`, `knowledge_catalog`, `expand_citation`, `impact_map`.
- **Authority Limits:** Read-only index authority; no Discord bot, tasks, tutoring, or mutation actions.
- **Memory Scope:** Dedicated Librarian working-memory peer.
- **Response Contract:** MCP envelope + compact citations.

### 4.3 `Researcher` (job-backed)
- **Purpose:** External technical research evidence via MCP.
- **Allowed Jobs:** `conduct_research` only.
- **Authority Limits:** No Discord bot, no task/tutor/mutation capabilities.
- **Memory Scope:** Dedicated Researcher working-memory peer.
- **Response Contract:** MCP evidence schema with claim/source structure.

### 4.4 `Assistant`
- **Purpose:** Discord personal assistant for task capture, light digests, and concise cited support answers.
- **Allowed Actions:** `manage_tasks` (delete requires `confirm_delete`), digest composition, internal Librarian/Researcher jobs.
- **Authority Limits:** No deep-dive tutoring; no plan/execute/push mutation workflow.
- **Memory Scope:** Dedicated Assistant working-memory peer.
- **Response Contract:** Markdown with compact citations when evidence is used; concise by default.

### 4.5 `Tutor`
- **Purpose:** Discord tutoring persona for deep-dive learning.
- **Allowed Actions:** tutoring requests plus internal Librarian/Researcher jobs.
- **Authority Limits:** No `manage_tasks`; no plan/execute/push mutation workflow.
- **Defaults:** `detail_level=deep_dive`; `language=cantonese_english_terms`; deep-dive responses avoid summarization shortcuts.
- **Memory Scope:** Dedicated Tutor working-memory peer.
- **Response Contract:** Markdown with code/research citations when evidence is used.

---

## 5. Coding-agent MCP Surface (Information-only)

> **Reader note:** This section follows ADR 0001/0002/0003: coding-agent MCP is persona-agnostic and information-only. No `agent_query`, `generate_plan`, `execute_plan`, `push_plan_pr`, `conduct_tutoring`, or `manage_tasks` on this server.

### 5.1 V1 MCP tools

```ts
library_search(query: string, repos?: string[], revision?: string, limit?: number)
session_brief(task: string, repos?: string[], focus?: "architecture" | "apis" | "tests" | "general")
knowledge_catalog(repos?: string[])
expand_citation(
  repo: string,
  revision: string,
  path: string,
  start_line: number,
  end_line: number,
  symbol?: string,
  context_lines?: number
)
impact_map(
  mode: "seed" | "intent",
  repo?: string,
  symbol?: string,
  path?: string,
  revision?: string,
  intent?: string,
  repos?: string[]
)
conduct_research(topic: string, sources?: string[], depth?: "quick" | "standard" | "deep")
```

### 5.2 Persona contract gate mapping

- `library_search`, `session_brief`, `knowledge_catalog`, `expand_citation`, `impact_map` map to **Librarian** jobs.
- `conduct_research` maps to **Researcher**.
- Out-of-scope MCP asks return typed `mcp_oos` in the shared response envelope.
- Optional operator-visible Main Agent escalation note is allowed for systemic repeated misuse; tool results are not silently rewritten.

### 5.3 Safety and boundary rules

- `manage_tasks` remains Discord-only.
- `conduct_tutoring` remains Discord-only.
- Plan/execute/push flow stays out of V1 persona roster and out of coding-agent MCP.
- Discord wrong-bot requests return refuse + hint only; no auto-handoff.

---

## 6. Observed VM State (Re-verified 2026-07-26)

> **Source:** Read-only SSH audit on VM `100.79.87.93` (uid `1001` / `ubuntu`). Full per-claim verdict table: [`docs/research/issue-39-discrepancy-ledger.md`](research/issue-39-discrepancy-ledger.md).

### 6.1 Runtime topology (confirmed wrong vs prior draft)
- Hermes **v0.15.1 (2026-05-29)** runs as a **host Python venv** at `/home/ubuntu/.hermes/hermes-agent/venv`, supervised by the systemd-user unit **`hermes-gateway.service`** (active 49 days, listening on `0.0.0.0:8642`). It is **not** in Docker.
- `/usr/local/bin/hermes` is a 19-line bash shim that sets `MEM0_DEFAULT_APP_ID` and execs the venv — not a Docker exec wrapper.
- `hermes-personal:latest` (2.29 GB) exists but is **orphaned** (no running containers from it).
- Open WebUI is reachable on Tailscale `http://100.79.87.93:3000` (HTTP 200).
- Dashboard is **not running** (no listener on port 9119).
- Install is **182 commits behind** upstream; `hermes update` is overdue.
- Source tree: full `NousResearch/hermes-agent` checkout, HEAD `f32b66c75`, ~1,716 `.py` files.

### 6.2 Directory inventory (re-verified)

| Path | Spec claim | Live (2026-07-26) | Notes |
|---|---|---|---|
| `/home/ubuntu/.hermes/` files / dirs | 34 / 26 | 34 / 26 | exact |
| `cron/` | 10,034 files | 10,246 | +212 stale |
| `hermes-agent/` | 55,850 files | 55,786 | within noise |
| `node/` | 29,037 files | 29,013 | within noise |
| `profiles/` | 1,313 files | 1,313 | exact |
| `sessions/` | 3,878 files | 3,878 | exact |
| `skills/` | 612 files | 612 | exact |
| `worktrees/` | (target path) | **absent** | must be created |
| `research/` | (target path) | **absent** | must be created |
| `logs/agent.log` | yes | yes (2.7 MB) | correct |
| `cron.log` | (mentioned) | **absent** | real output is `cron/output/<job-id>/<timestamp>.md` (10,245 files) |

### 6.3 Provider & gateway configuration

| Setting | Live value | Status |
|---|---|---|
| `model.default` | `MiniMax-M3` | Default confirmed |
| `model.provider` | `minimax-cn` (base `https://api.minimaxi.com/anthropic`) | Confirmed |
| Delegation provider | `openrouter` | Confirmed |
| Delegation model | `deepseek/deepseek-v4-flash` via OpenRouter | **DEBT** — breaks the "MiniMax-only" non-negotiable (see §8) |
| Fallback chain | `['openrouter','openai-codex','deepseek']` | Confirmed exact; also **DEBT** |
| `channel_directory.json` Telegram `gncsbot` | ID `6396579368` | Still present on VM; **out of V1** (D-DISC-1) |
| Discord `.env` keys | `DISCORD_BOT_TOKEN`, `DISCORD_HOME_CHANNEL`, `DISCORD_ALLOWED_USERS` all present and truthy | Confirmed; V1 Assistant channel |
| Telegram `.env` keys | `TELEGRAM_BOT_TOKEN` present; no `TELEGRAM_ALLOWED_USER_ID` | Legacy; disable / ignore for V1 |
| `GATEWAY_ALLOW_ALL_USERS` | literally `true` | Broader gateway flag still permissive — **DEBT** for Discord allowlist enforcement hardening (D-DISC-1 follow-through) |

### 6.4 Database & memory findings (re-verified)

- `state.db` is a valid SQLite 3 database, ~99 MB. Tables: `messages`, `sessions`, `compression_locks`, `messages_fts*` (incl. trigram), `schema_version`, `state_meta`, `sqlite_sequence`.
- `messages`: **7,060** — exact. `sessions`: 2,177 rows, **2,174 distinct message-linked session IDs**.
- All three named tutor sessions exist and are intact: `20260515_140232_e5cae2` (64 msgs), `20260515_175823_864500` (66 msgs), `20260516_004506_fb9729` (49 msgs).
- All six named message IDs (879 / 889 / 893 / 905 / 960 / 1035) exist, all user-role, all containing real Cantonese / LangGraph / Hypthon-HK / "university-tutor deep-dive" content that the §1.6 contract was inferred from.
- Profiles & skill categories are **filesystem**, not `state.db` records: 4 profile dirs (`coder`, `council`, `research`, `runner`) and 33 visible skill categories after excluding `.archive`, `.curator_backups`, `.hub`.
- `memories/MEMORY.md` and `USER.md` contain real persistent facts (travel, hair products, Nagasaki gifts, `agentmemory` server v0.9.24 reference).
- `kanban.db` exists with 7 tables (`tasks`, `task_links`, `task_comments`, `task_events`, `task_runs`, `kanban_notify_subs`, `sqlite_sequence`); **all tables empty** — primary table is `tasks`, not `tickets`. Suspicious for a delegation store; needs cold-start confirmation.

### 6.5 Memory stack & adjacent services (observed — cleanup deferred to #41)

> **Framing:** #39 does **not** pick a winner among these. Consolidation / replacement is the job of ticket **#41** (memory system evaluation). Only **agentmemory** has a #39 decision: uninstall (D-MEM-3). **Ollama is not a memory service** — it is local LLM/embedding inference and is listed separately below.

| Component | How | State | #39 stance |
|---|---|---|---|
| **Qdrant** | Docker `qdrant_mem0` | Up 7 weeks; 127.0.0.1:6333/6334; collections `mem0`, `mem0_nomic`, `mem0migrations`, `terraforming` | MEM-7 uninstall (hybrid close 2026-07-27) |
| **mem0** | `~/.hermes/mem0.json` (thin: `user_id`/`agent_id`/`rerank`) | Backed by `qdrant_mem0` | MEM-7 uninstall (hybrid close 2026-07-27) |
| **Honcho** | Docker compose (api/deriver/redis/pgvector) | Up 8 weeks; 127.0.0.1:8000; Postgres on `127.0.0.1:5432` (untouched by #47) | MEM-2 retained as V1 working-memory provider |
| **neo4j** | Docker `neo4j` | Up 7 weeks; 7474/7687; 2026.04.0 community | MEM-5 uninstall (hybrid close 2026-07-27) |
| **agentmemory** | systemd `agentmemory.service` + `iii` | Active; ports 3111/3112/49134 (+ health on 8642-adjacent path) | **D-MEM-3: uninstall entirely before #39 closes** |
| **Hermes Postgres** | systemd `postgresql-16` + `postgresql-16-pgvector` (apt) | Live on `127.0.0.1:5433` since 2026-07-27; two DBs (`hermes`, `codebase_index`) with dedicated LOGIN owners (`hermes_app`, `codebase_index_app`); pgvector extension enabled on `codebase_index`; V1 schema migrated (`0001_init.sql` for both DBs). Honcho's `:5432` untouched. | **#47 landed — MEM-3/MEM-4 carrier; not a V1 memory service in itself, but the substrate for the codebase index (#40) and Hermes audit/research/session/digest tables (#6.5, §10)** |

**Not memory — local inference (do not treat as memory stack):**

| Component | How | State | Note |
|---|---|---|---|
| **ollama** | Native (not docker) | 127.0.0.1:11434; models include `nomic-embed-text`, `gemma4:e4b`, `qwen3.6`, `qwen3.5:9b` | Embedding/LLM host used by other services; **not** a memory backend |

### 6.6 Persona & profile reality

- `SOUL.md` body is **effectively empty** (only a commented example block); no live persona content.
- Profile directories (`profiles/`): `coder`, `council`, `research`, `runner`. **No `default` persona profile exists.** These are role/task containers, not personality personas.
- The 6-persona roster in §4 is a **V1 target contract**, not current behavior.

### 6.7 Cron & ops reality

- `cron/jobs.json` contains 4 jobs: `Backup Neo4j to Google Drive`, `ollama-keep-alive`, `weekly-workspace-cleanup`, `vm-health-check`.
- `vm-health-check`: **healthy** (56 runs, last OK 2026-07-25).
- `weekly-workspace-cleanup`: defined but currently **failing with 401 auth** on an API key ending `f14d` (DEBT).
- `vm_health.sh` is at `/home/ubuntu/.hermes/scripts/vm_health.sh` (not `cron/vm_health.sh`).
- `crontab`/`sqlite3` CLIs are **not installed** on the VM; Hermes cron is in-process (JSON-driven), with no system crontab and no systemd timers.
- `agent.log` is at `/home/ubuntu/.hermes/logs/agent.log` (2.7 MB, modified 2026-07-25 18:11).

### 6.8 MCP tooling reality

- Infrastructure **present**: `mcp_serve.py`, `tools/registry.py`, `tools/mcp_tool.py`, `tools/delegate_tool.py`, `tests/tools/test_mcp_*.py`, plus 49 CLI subcommands including `mcp`, `tools`, `kanban`, `memory`, `skills`.
- The 8 spec-named tools (`library_search`, `generate_plan`, `execute_plan`, `push_plan_pr`, `conduct_research`, `conduct_tutoring`, `manage_tasks`, `agent_query`) — **0 matches** in source, config, `AGENTS.md`, or CLI. None are registered today.

### 6.9 Tailscale listener surface (re-verified — wider than spec implies)

TCP reachable on Tailscale `100.79.87.93`:

- `22` — SSH
- `80` / `443` — nginx
- `111` (TCP + UDP) — rpcbind
- `3000` — Open WebUI (Docker proxy)
- `3080` / `3081` — geo-auditor backend / web UI containers
- `3111` / `3112` — AgentMemory/`iii`
- `62773` — tailscaled
- `8642` — Hermes gateway
- `49134` — `iii` worker service

Tailscale-only UFW allows the 3000-range AgentMemory ports; port 8642 has direct host iptables accept rules.

**D-EXP-1 = A (accepted Tailscale services for V1):** SSH `22`, tailscaled `62773`, Hermes gateway `8642`, Open WebUI `3000`. **Removal (D-MEM-3):** AgentMemory `3111`/`3112`/`49134` are being uninstalled, not accepted. **Cleanup debt (not #39 blockers):** nginx `80`/`443`, geo-auditor `3080`/`3081`, rpcbind `111`. Non-negotiable = no internet-public exposure; Tailscale-internal allowlist above is intentional.

---

## 7. User-Confirmed HITL Decisions (Q1–Q12)

> **Reader note:** These were **user-confirmed decisions** from the grilling sessions — distinct from VM-confirmed facts in §6. Treat Q1–Q12 as the **intentional V1 contract**, with §6 grounding the implemented parts.

- **Q1**: Multi-repo cross-cutting search for Knowledge Retrieval.
- **Q2**: Synthesized Markdown + revision-anchor response format.
- **Q3**: Two-stage execution model (`generate_plan` → `execute_plan`).
- **Q4**: Isolated Git worktree + feature branch (`hermes/plan-<id>`).
- **Q5**: Structured report artifact + memory indexing.
- **Q6**: Background cron digest + personal assistant in V1; PopIdea deferred.
- **Q7**: 6-persona roster design.
- **Q8 & Q8.1**: Persona-aligned typed tool suite + mandatory confirmation flags + allowlisted chat privacy (originally Telegram; superseded by Q13).
- **Q9**: Standalone `Tutor` persona + `conduct_tutoring` tool.
- **Q10**: Sequential execution of downstream tickets (#40–#44).
- **Q11**: Ticket #40 hybrid local-mirror + incremental-index architecture.
- **Q12**: Ticket #40 80 GB disk budget (shallow clones, sparse checkouts, source files only, LRU eviction at >80 GB).
- **Q13 (D-DISC-1 = A)**: Discord home channel + `DISCORD_ALLOWED_USERS` is the only end-user chat surface in V1. Telegram is turned off for V1 (fully out of scope).

---

## 8. Non-Negotiables (From handoff)

> **Status check 2026-07-26:** Four of these are **DEBT** today.

- **MiniMax-M3 only.** No fallback chain, no OpenRouter, no DeepSeek, no Codex.
  - **DEBT:** `model.default = MiniMax-M3`, but delegation uses `deepseek/deepseek-v4-flash` via `openrouter` with fallback chain `['openrouter','openai-codex','deepseek']` (live). Spec §6.3 already documents this conflict; §8 enforces the intent. **D-NN-1 = A:** non-negotiable KEPT; live multi-provider delegation is DEBT; #39 cannot close until `config.yaml` `delegation.provider` and `fallback_providers` are MiniMax-only (or removed).
- **Self-hosted** on the VM at `/home/ubuntu/.hermes/`. Confirmed.
- **Tailscale** for all cross-PC traffic. Zero **internet-public** exposure.
  - **D-EXP-1 = A:** Non-negotiable is internet-edge privacy, not “SSH-only on Tailscale.” Accepted Tailscale-internal listeners for V1 ops: SSH (`22`), tailscaled (`62773`), Hermes gateway (`8642`), Open WebUI (`3000`). AgentMemory `iii` (`3111`/`3112`/`49134`) is **being removed** (D-MEM-3), not accepted. Non-Hermes leftovers (nginx `80`/`443`, geo-auditor `3080`/`3081`, rpcbind `111`) are **cleanup debt**, not #39 blockers — document in §6.9, do not invent new public exposure.
- **MCP tool surface** as the consumer surface.
  - **DEBT:** Infrastructure is present; 8 named tools are not registered (see §5, §6.8). D-CAP-1.
- **General-purpose codebase wiki** sourced from GitHub. Confirmed intent; not yet indexed (separate #40 ticket).

---

## 9. Out of Scope (V1)

- Cloud/remote memory.
- Public exposure of any service.
- Multi-region / HA.
- New desktop or mobile shells.
- User-created personas.
- **PopIdea app integration with the Assistant persona** — explicitly deferred to issue #46. Do not start this work in V1; track progress under #46.
- **Telegram** as an end-user or Assistant channel — turned off for V1 (D-DISC-1 = A). Legacy `gncsbot` / `TELEGRAM_BOT_TOKEN` may remain on the VM but must not be invoked by V1 contracts.

---

## 10. Response Needs Summary (V1 Target)

| Use Case | Shape | Citation Density | Length Envelope | Failure Format |
|---|---|---|---|---|
| Knowledge Retrieval | Synthesized Markdown | file:line anchors per claim | ≤ 800 tokens | `NOT_FOUND` with suggested rephrasing |
| Code Plan Generation | JSON/Markdown plan spec | n/a | ≤ 1500 tokens | `PLAN_INVALID` with rejected step |
| Code Plan Execution | Commit hash + verification output | n/a | ≤ 300 tokens | `EXECUTION_FAILED` with rollback hint |
| Research (public) | Executive summary + artifact path | sources array | ≤ 500 tokens summary | `RESEARCH_FAILED` with retry hint |
| Research (private) | Executive summary only (no shared indexing) | none | ≤ 500 tokens | same as public |
| Cron Digest | One-line status per check | n/a | ≤ 200 tokens | per-check status |
| Discord Task List | Bullet list | n/a | ≤ 100 tokens | empty list is valid |
| Tutor Deep Dive | Full Markdown breakdown, no `[[...]]` shortcuts | file:line anchors | unbounded (full code) | n/a |

---

## 11. Open Debt Items

> **D-CLOSE-1 = C (hybrid close):** #39 closes after live verify of MiniMax harden + AgentMemory uninstall + Telegram-off/Discord-only. **Those three were verified on the VM 2026-07-27.** Cron 401 and empty `worktrees/`/`research/` dirs remain non-blocking follow-ups.

### Blocking for #39 close (must verify on VM)

1. **D-NN-1** MiniMax-only — `VERIFIED 2026-07-27` on VM: `fallback_providers=[]`, `delegation.provider=minimax-cn`, `delegation.model=MiniMax-M3`, `model.default=MiniMax-M3`. Backup: `config.yaml.bak.20260727T024441Z`.
2. **D-DISC-1** Discord-only — `VERIFIED 2026-07-27` on VM: `gateway.platforms.telegram.enabled=false`, `TELEGRAM_BOT_TOKEN` renamed to `TELEGRAM_BOT_TOKEN_DISABLED`, `GATEWAY_ALLOW_ALL_USERS=false`, `discord.allowed_channels`/`free_response_channels`=`1510315295024218182`, `discord.allowed_users`=`495257815057694720`. Backup: `.env.bak.20260727T024441Z`.
3. **D-MEM-3** AgentMemory uninstall — `VERIFIED 2026-07-27` on VM: service inactive/not-found; unit moved to `agentmemory.service.disabled.20260727T024441Z`; `iii` + `~/.agentmemory` moved to `*.disabled.20260727T024441Z`; ports `3111`/`3112`/`49134` gone; Hermes gateway still active on `8642`.

### Non-blocking follow-ups (do not hold #39 close)

4. **D-GW-1** Telegram 1:1 allowlist — `SUPERSEDED by D-DISC-1`.
5. **D-EXP-1** Tailscale surface — `RESOLVED: A` (documented allowlist; leftovers = cleanup debt).
6. **D-RUN-1** Runtime topology — `RESOLVED: A`.
7. **D-CAP-1** MCP tool names — `RESOLVED: A` (target surface; build is implementation, not #39).
8. **D-CRON-1** `weekly-workspace-cleanup` 401 (`****f14d`) — triage as separate ops ticket; §1.4 “working” stays qualified until fixed.
9. **D-CRON-2** Empty `kanban.db` — non-blocking note.
10. **DIR-9/UC-1** Create `/home/ubuntu/.hermes/worktrees/` and `research/` — V1 build / ops follow-up.
11. **MEM-2 / memory-stack cleanup** — RESOLVED by #41 MEM-1…8 hybrid close; follow-ups (Postgres provisioning, Drive portable restore) tracked separately.
