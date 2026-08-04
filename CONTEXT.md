# Hermes Domain Glossary

## Persona

A distinct Hermes operating identity for a recurring kind of work. Each persona has its own purpose, tools, authority, memory scope, and response contract. It is not merely a prompt variation. In V1, which personas are *callable* vs *job-backed* is defined by the entrypoint model (see Persona selection).

## Job-backed persona

A persona with no Discord bot of its own. Hermes applies its contract when a matching MCP job runs (Librarian for codebase-info tools; Researcher for `conduct_research`). Any authorized Tailscale MCP consumer may call those tools; callers do not select the persona by name.
_Avoid_: Discord bots for job-backed personas; requiring `agent_query(persona=…)` to use their tools; restricting Librarian/Researcher MCP jobs to one consumer beyond Tailscale auth

## Persona selection

V1 selects Discord personas by **which bot is @-mentioned** (one Discord application/bot per Discord-reachable persona). Cron/ops jobs also run as Main Agent without Discord. Coding-agent MCP tools are persona-agnostic (no `persona` field, no `agent_query`); Librarian and Researcher contracts attach when their MCP jobs run. `conduct_tutoring` is **not** registered on the coding-agent information MCP server.
_Avoid_: persona param on every MCP tool; resurrecting `agent_query` on the coding-agent MCP; Telegram as an Assistant/Tutor entrypoint; registering `conduct_tutoring` on the coding-agent MCP suite; one shared Discord bot that infers Assistant vs Tutor vs Main Agent

## Discord persona bots

V1 ships **three** Discord bots — **Assistant**, **Tutor**, and **Main Agent**. The user @-mentions the bot they want on the shared Discord home channel. Librarian and Researcher have **no** Discord bot; they are reached only through coding-agent MCP jobs, callable by any authorized Tailscale MCP consumer.
_Avoid_: five Discord bots in V1; intent-classifier routing on a single bot; Discord bots for Librarian/Researcher; requiring separate channels per bot in V1

## Contract gate integration

This repo's `hermes/personas/` package (contract gate + adapters) is a
dependency-free policy layer imported by this repo's own runtime,
`hermes_agent/`, which is the V1 gateway (D-B fork 2, ADR 0004 amendment
2026-08-04 — the external hermes-agent gateway was lost with the old VM;
the "not a replacement runtime" stance is superseded). `hermes_agent`'s
Discord and MCP handlers call `route_discord_message()` /
`route_mcp_tool()` before dispatching, then run the approved action
against MiniMax-M3, Honcho, and the codebase index. The policy module is
validated against the runtime's message/tool shapes by the VM smoke gate
(map #76 Task 5 acceptance: gateway up + enabled, three bots answer
@-mention).
_Avoid_: running a second Discord listener process alongside
`hermes-gateway.service`; treating the policy module as
production-validated before the VM smoke gate passes

## confirm_delete UX (deferred — design captured, not implemented)

`manage_tasks` delete confirmation, once built: a native Discord button prompt (`discord.ui.View` with Yes/No, reusing the existing `ExecApprovalView` interaction pattern already in hermes-agent's Discord adapter), sent via `gateway.adapters[Platform.DISCORD].send(...)` from within the `pre_gateway_dispatch` hook, not a text-reply confirmation phrase. The button click is a Discord interaction, not a `MessageEvent` — requires a separate interaction handler (not `pre_gateway_dispatch`) to catch the click and re-invoke the contract gate with `confirm_delete=True`. No interaction handler, view class, or wiring code exists yet; this term records the UX decision only.
_Avoid_: text-phrase confirmation ("reply yes to confirm") as the V1 mechanism; treating this term as evidence the feature is built; inventing a second confirmation pattern when ExecApprovalView already exists in the same codebase

## Tutor entrypoint

Invoking the Tutor Discord bot (@-mention) on the Discord home channel. Tutoring runs under the Tutor persona contract (deep_dive defaults, Librarian + Researcher job tools). Bot identity — not prompt inference — chooses Tutor vs Assistant vs Main Agent.
_Avoid_: Tutor-only Tailscale MCP as the V1 entrypoint; Open WebUI as the required V1 Tutor surface; mixing Tutor into coding-agent MCP tools; `/tutor` prefix on the Assistant bot as the primary V1 mechanism

## Main Agent

The V1 ops, escalation, and **Discord super-set** persona. Owns cron/health digests, system-monitoring summaries, and operator-facing housekeeping. Its Discord bot may do everything Assistant and Tutor can (tasks, digests, deep-dive tutoring, Librarian/Researcher jobs) **plus** ops/escalation actions. It does not answer coding-agent MCP calls directly (those tools still apply Librarian/Researcher contracts). Assistant and Tutor remain separate bots with narrower defaults and isolated working memory.
_Avoid_: Main Agent as the only Discord bot; Main Agent as coding-agent MCP narrator; deleting Assistant/Tutor bots because Main Agent can cover them

## Assistant (persona)

Discord bot for personal notes, tasks, light digests, and cited codebase/research answers. Allowed capabilities: `manage_tasks` (delete requires `confirm_delete`); personal digest composition from allowlisted sources; **internal** calls to Librarian jobs and Researcher jobs (same contracts as MCP — read/research only). Does not tutor deep-dive, mutate worktrees, or open PRs.
_Avoid_: Assistant as Tutor; Assistant as implementor; registering Assistant-only tools on the coding-agent MCP server

## Tutor (persona)

Discord bot for academic / exam / internship tutoring. Defaults: `detail_level=deep_dive`, `language=cantonese_english_terms`; in deep_dive, **zero summarization** (full step-by-step, no “refer to the docs”). May use Librarian jobs and Researcher jobs as internal tools for code anchors and external sources. No `manage_tasks`, no worktree/PR mutation.
_Avoid_: Tutor as task manager; Tutor as implementor; shallow overview as the V1 default detail level

## Persona delegation

Assistant and Tutor may invoke Librarian/Researcher **jobs as tools** during a Discord turn (not by @-pinging a Librarian bot — none exists). Job-backed personas do not peer-delegate. No silent bot-to-bot switch mid-turn — if a specialist is out of scope, it **refuses** with a hint; the user may @Main Agent directly (super-set authority).
_Avoid_: unrestricted silent persona hopping; Assistant @-mentioning Tutor to finish a turn without user action; auto-handoff to Main Agent

## Persona memory

Each of the five V1 personas has **isolated working memory** (Honcho peer): Main Agent, Librarian, Researcher, Assistant, Tutor. The shared codebase knowledge layer and Hermes DB facts are available per contract. Cross-persona handoffs carry explicit task context only — private peer memory is not exposed by default. Main Agent’s super-set Discord authority does **not** grant read access to Assistant/Tutor peer memory.
_Avoid_: one shared Discord chat peer for Assistant+Tutor+Main Agent; auto-merging specialist memory into Main Agent; treating Honcho as codebase SoT

## Librarian (persona)

Job-backed persona for codebase information work. Purpose: cited retrieval, briefs, catalog/freshness, citation expansion, and impact maps over the codebase index. Authority: read-only over the index; no Discord bot; no tasks/tutoring/mutations. Response: coding-agent MCP envelope when called via MCP; when invoked as an internal job from a Discord bot, evidence returns to that bot’s narrator under the same retrieval contracts.
_Avoid_: Librarian as Discord bot; Librarian as implementor

## Researcher (persona)

Job-backed persona for external/technical research via `conduct_research`. Authority: research evidence only; no Discord bot; no codebase mutation; no `manage_tasks`. Response: MCP evidence schema when called via MCP; same job contract when invoked internally from Discord.
_Avoid_: Researcher as Discord bot; Researcher as Tutor; path-only research results as the caller contract

## V1 persona set

V1 ships five fixed personas: **Main Agent**, **Librarian**, **Researcher**, **Assistant**, and **Tutor**. User-created personas are outside the V1 boundary. **Developer** is out of V1 — no implementor persona while the coding-agent MCP is information-only (#42).

**Librarian** and **Researcher** are **job-backed contracts**: named personas with purpose, authority, isolated working memory, and response rules applied when their MCP jobs run. No Discord bot; MCP-callable by any authorized Tailscale consumer.

**Librarian jobs (V1):** `library_search`, `session_brief`, `knowledge_catalog`, `expand_citation`, `impact_map`.  
**Researcher jobs (V1):** `conduct_research` only.
_Avoid_: Developer as a V1 persona; treating the #39 six-persona draft as still binding; user-created personas in V1; Discord bots for Librarian/Researcher; assigning session_brief or impact_map to Main Agent

## Hermes V1 planning destination

This wayfinder map ends at an implementation-ready Hermes V1 specification and dependency-ordered execution plan. Deployment on the user's VM follows as implementation, not as part of the planning map.

Use-case research must actively discover additional ways Hermes fits the user's life beyond knowledge retrieval, code-plan implementation, and research. Those findings shape the fixed V1 persona set and MCP surface.

## Discord response contract

V1 Discord bot replies are Markdown prose. When codebase or research evidence is used, the reply includes compact citation lines (`repo@rev path:start-end` or source URIs for research). Tutor deep_dive replies may be long; Assistant and routine Main Agent ops replies stay short unless the user asks for depth.
_Avoid_: MCP JSON envelopes as Discord messages; citation-free code claims as the default; forcing every Assistant ack to include citations

## manage_tasks

Discord-only task capability used by Assistant and Main Agent bots: list / add / complete / delete. Delete requires `confirm_delete`. Not registered on the coding-agent information MCP server.
_Avoid_: manage_tasks on the coding-agent MCP suite; task mutations without confirm_delete for delete

## Persona contract

A source-managed definition for one persona. It states the persona's purpose, allowed tools, authority limits, memory scope, delegation rules, response format, and acceptance scenarios. Each fixed V1 persona must have a contract.

## V1 persona acceptance scenarios

Checklist that must pass for the V1 persona roster:
- **Librarian** — coding-agent codebase-info tools return the MCP envelope + citations; mutation/task asks → typed OOS (optional systemic ops note).
- **Researcher** — `conduct_research` returns the evidence schema; no worktree edits; Discord-internal research uses the same job rules.
- **Assistant** — `@Assistant` tasks (`confirm_delete` on delete), digests, cited code/research answers; tutor deep-dive asks → refuse + hint.
- **Tutor** — `@Tutor` deep_dive Cantonese+English-terms lessons with citations when evidence is used; `manage_tasks` → refuse + hint.
- **Main Agent** — cron digests without Discord; `@Main Agent` may perform Assistant∪Tutor∪ops; coding-agent MCP is never narrated as Main Agent.
- **Selection** — no @ → ignore; wrong bot → refuse only; no Librarian/Researcher Discord bots.
- **Memory** — five isolated Honcho peers; Main Agent super-set does not share Assistant/Tutor diaries.
_Avoid_: treating #39 six-persona + plan/execute acceptance as still binding

## Persona authority boundary

A specialized persona must not silently act beyond its contract. When a request exceeds its authority, it returns an explicit out-of-scope result.

**Discord specialists (Assistant, Tutor):** **refuse only** — short OOS reply plus a hint to @ the right bot (or use MCP). No automatic Main Agent handoff and no silent bot switch.

**Job-backed MCP OOS:** Librarian/Researcher tools return typed out-of-scope to the MCP caller (`ok: false` / envelope errors). Hermes may also write an **operator-visible Main Agent escalation note** (audit/digest, and/or Main Agent Discord) when the miss looks systemic. Main Agent never silently rewrites the tool response.
_Avoid_: silent specialist-to-specialist handoff; auto-rerouting an MCP call to Assistant/Tutor; Main Agent silently rewriting an MCP tool response; Assistant/Tutor auto-continuing as Main Agent

## MiniMax-only

Provider policy: Hermes may call MiniMax-M3 only. No OpenRouter, Codex, or DeepSeek fallback is permitted.

## Discord home channel

The single Discord channel (`DISCORD_HOME_CHANNEL`) where the Assistant, Tutor, and Main Agent bots all listen. Only the @-mentioned bot responds; messages with no Hermes bot mention are ignored. Same user allowlist for all three bots in V1.
_Avoid_: reacting without an @-mention; per-bot required channels in V1; Telegram as home channel

## Assistant channel

Synonym in practice for Discord home-channel work aimed at the Assistant bot (@-mention). Allowlisted users only.
_Avoid_: Telegram; DM-only Assistant gateway; treating unmarked messages as Assistant work

## Memory stack (V1)

The set of services that persist and retrieve persona/shared knowledge. Under **MEM-1**, Hermes owns canonical truth in a **Hermes database**; processed repository knowledge lives in a separate **codebase index database**. Honcho provides personal working memory. Mem0, standalone Qdrant, agentmemory, and neo4j are out of V1.
_Avoid_: one combined DB for Hermes ops and repo wiki; treating Ollama as memory; Mem0/Qdrant/agentmemory/neo4j as V1 memory

## Hermes database

Durable Postgres store for Hermes itself: canonical records, audit/events, research evidence, persona/task scope metadata, session-brief pointers, structured digests/allowlists (not codebase chunks; not Honcho’s peer graph). Lives in a **dedicated Hermes Postgres instance** managed by **systemd/apt** (not Docker, not Honcho’s container), as one of two logical databases on that instance.
_Avoid_: storing full repo indexes here; peer-chat wiki as SoT; SQLite as the V1 Hermes canonical engine; sharing Honcho’s Postgres for Hermes canonical data; Docker Compose for the Hermes Postgres engine

## Codebase index database

Durable Postgres store (+ pgvector + FTS) for processed coding repositories: commit-addressable paths, symbols, chunks, lexical + semantic retrieval over the #40 knowledge layer. Same dedicated Hermes Postgres instance as the Hermes database, separate logical DB and role. Read by all personas; writable only through controlled ingestion.
_Avoid_: persona-private notes; mixing with Hermes operational tables; Qdrant-as-sole code SoT; co-locating in Honcho’s Postgres

## Session brief

A compact, citation-backed sum-up Hermes returns at session start (or on demand) so callers spend fewer tokens rediscovering codebase/task context. Built from the codebase index database and an explicit task seed (optional repo filters and optional focus), not from peer-chat modeling alone.
_Avoid_: dumping full chat history; uncited "what I remember" narratives as the brief; requiring Honcho preferences to build the V1 brief

## Ops digest (deferred — design captured, not implemented)

Main Agent's `run_ops_digest` action, once built: writes a durable record to the **Hermes database** `digests` table (satisfying the existing structured-digests commitment in the Hermes database term) AND proactively posts the same content to the Discord home channel via the `main_agent` profile's adapter. Both destinations, not one — durability plus visibility. Cadence: daily, staggered one hour after the existing `vm-health-check` cron job (`0 7 * * *` vs `vm-health-check`'s `0 6 * * *`) so the digest can consolidate that morning's health-check result rather than racing it. Content: full consolidation — every registered cron job gets a one-line status entry (not just health checks, not failures-only), matching the existing `≤ 200 token` / "one-line status per check" budget in `docs/use-case-specification.md` §10. On first deploy this will immediately surface `weekly-workspace-cleanup`'s pre-existing 401 auth failure (§6.7) — expected behavior, not a bug to fix as part of this ticket. No cron job, table schema, or send-path code exists yet; this term records the destination, cadence, and content-shape decisions only, for whoever picks up the cron/digest ticket.
_Avoid_: Discord-only (loses history); Hermes-DB-only (operator must ask); weekly cadence (stale for same-day issues); health-only or failures-only content (excludes real signal); full per-job output dumps (blows the token budget — one line per job, not a report); treating this term as evidence the feature is built

## session_brief

The MCP tool that produces a Session brief for the Mac coding agent. V1 input: required `task`; optional `repos[]`; optional `focus` (`architecture` | `apis` | `tests` | `general`, default `general`). V1 corpus: codebase index only. Start-work: deterministic retrieve/rank of anchors in code; MiniMax writes `{ brief_markdown, sections?: [{ title, bullets[] }] }` grounded in those hits, plus top-level `citations[]`.
_Avoid_: Honcho-only briefs; brief-with-no-task as the V1 default; requiring revision on the V1 brief caller contract; MiniMax-planned retrieval for briefs; fully template-only briefs with no model narration

## conduct_research

The MCP tool for external/technical research aimed at the Mac coding agent. Caller input: required `topic`; optional `sources[]` hints; optional `depth` (`quick` | `standard` | `deep`). Response `data`: `{ summary_markdown, claims: [{ claim, confidence, sources[] }], sources: [{ uri, title?, excerpt? }] }`. Start-work: hybrid — code does initial fetch from hints; MiniMax may request one follow-up fetch round for gaps, then fills the evidence schema. Persisting Markdown under Hermes `research/` may be an internal archive side effect; callers must not depend on a VM path. Because Hermes is personal-use, V1 research from this tool is shared-eligible (no `sensitivity` private mode on the coding-agent MCP contract).
_Avoid_: path-only research results; free-form essay with no evidence schema as the V1 contract; requiring a public|private sensitivity flag on V1 coding-agent research calls; overloading the caller contract with question-type enums; unbounded MiniMax-driven web tool loops

## Working memory (V1)

Persona-private task state, chat-derived preferences, and cross-session interaction context. In V1 this role is filled by Honcho (peer/session representations), not Mem0. It is not the source of truth for codebase or research facts.
_Avoid_: Mem0 as required V1 working-memory SoT; conflating working memory with the shared knowledge layer or codebase index

## Personal advisor (V1)

Assistant workload beyond Discord task capture: topic digests (tech, AI, other fields, stocks-related news) and eventual email-reading help. Continuity and preferences live in working memory (Honcho); structured digest artifacts and allowlists live in the Hermes database.
_Avoid_: stuffing news corpora into Honcho as a wiki; treating PopIdea (#46) as required for this V1 surface

## Local inference

On-VM model serving used for embeddings or generation (today: Ollama). Distinct from the memory stack.
_Reboot (D-C, 2026-08-04):_ the target (Oracle Cloud free tier, 2 CPU / 12 GB RAM) runs Ollama for **embedding-class** models only — `nomic-embed-text` (137M params) benchmarks at ~1 s/chunk, 768-dim, ~40 MB RSS. LLM-class models stay remote (MiniMax-M3, D-D); the earlier "Ollama cannot run" premise (ADR 0005/0006) applied to 7B-class sizes. Ollama serves `127.0.0.1:11434` only (zero public exposure).

## Install contract (reboot)

The settled way Hermes gets installed from this repo (ADR 0005, ticket #80): a thin `setup/install.sh` chains the existing deterministic scripts (Postgres provision → smoke gate → indexer → restore-if-backup → final smoke), and a top-level `INSTALL.md` runbook carries the unscripted tail (Tailscale up, `.env` creation, gateway bring-up, profile apply, cron registration). A coding agent runs the script, then follows the runbook. Redo = re-clone/re-run from the top; the bootstrap halts on the first failing smoke.
_Avoid_: Docker Compose as the install mechanism; idempotency machinery; requiring a Drive restore on the happy path

## Fresh install (zero-data)

The reboot starts with no durable state: the old VM is deleted and the Drive backup was never built. Secrets come from a committed `.env.example` template: the installer copies it to `.env`, validates every required key, and fails fast listing what is missing. The age-key/Drive backup-restore chain is retained as scripted DR only and is **unverified** (never executed end-to-end; prototype #77 dry-runs it).
_Avoid_: treating the restore chain as a tested path; committing real tokens; requiring an age key for a first install

## Install acceptance (reboot)

The definition of "working Hermes" after install (ADR 0005): `smoke-hermes-postgres.sh` passes (Hermes DB + codebase-index DB on `:5433`, pgvector); gateway service up and systemd-enabled; Assistant, Tutor, and Main Agent Discord bots answer an @-mention; cron jobs registered; indexer completes a first sync; `library_search` returns the MCP envelope; `.env` validation clean. Ollama embeddings (D-C) are part of the stack: `nomic-embed-text` on `127.0.0.1:11434`, Honcho embedding config pointed at it.
_Avoid_: treating an empty index or a silent gateway as success; blocking install on an LLM-class local model

## Target environment (reboot)

The fresh Hermes install runs on Oracle Cloud free tier, **Ampere A1 (ARM, 2 OCPU / 12 GB RAM)**, **Ubuntu 24.04 LTS aarch64** (ADR 0006, ticket #78). The VM was created manually in the Oracle console — install artifacts stay provider-agnostic (apt/systemd/SSH/Tailscale only, no OCI tooling). The E2.1.Micro shape is too small; Oracle Linux 9 was rejected because it would force porting the apt-based provision scripts to dnf + PGDG.
_Avoid_: OCI CLI automation in v1; Oracle Linux / RHEL-family baseline; a local machine as the target (breaks the D2 redo-semantics assumption)

## Tailscale-internal surface

Services intentionally reachable on the Tailscale mesh (not the public internet). V1 accepts SSH, tailscaled, Hermes gateway, and Open WebUI on that mesh. AgentMemory ports are removal targets. Leftover listeners are cleanup debt, not a rewrite of the zero-public-exposure rule.

## Hybrid close

For use-case research tickets: close after the accepted spec is written **and** a short list of live VM hardening checks pass; remaining ops may follow as separate tickets.

## Portable restore

The ability to stand up Hermes on a new machine by cloning from GitHub and restoring durable databases from Google Drive backups, so a deleted VM is not a total loss. V1 backup set: Hermes Postgres, codebase-index Postgres, Honcho Postgres. Secrets travel as an **encrypted archive on Drive**; a separate **unlock key file** (never uploaded to Drive) is required to decrypt. On restore, the operator points the agent or restore script at that key file.
_Avoid_: treating the Oracle VM disk as the only copy of truth; Neo4j dumps as the recovery path; putting plaintext `.env`/tokens in the public repo or unencrypted on Drive; storing the unlock key on Drive

## Unlock key file

A generated **`age` identity** (private key file) that decrypts the Drive-stored encrypted secrets archive. It is kept offline / off-Drive; the operator supplies its path when importing secrets onto a new machine. Contents of the archive: minimal Hermes runtime secrets (`.env` / token export + rclone config as needed).
_Avoid_: embedding the key in the Drive archive; committing the key to git; using a Drive-stored passphrase as the only secret; stuffing full `~/.hermes/` into the archive

## Schema migrations (Hermes)

Versioned SQL files in this repository that create and alter the Hermes database and codebase index database. Applied on the VM with `psql` (not Alembic against hermes-agent).
_Avoid_: one-shot undocumented bootstrap; coupling V1 schema to upstream hermes-agent ORM

## MCP tool surface

The set of named MCP tools Hermes exposes to coding agents and other Tailscale consumers. V1 uses an explicit suite of tools, each with its own input/output contract and authority boundary — not a single routing primitive. The V1 Tailscale MCP server registers the coding-agent information suite only; Discord Assistant, Tutor, and operator/cron stay on non-MCP entrypoints.
_Avoid_: one mega-tool as the only surface; collapsing authority into free-form prompt text; registering manage_tasks / conduct_tutoring / plan-execute tools on the V1 coding-agent MCP server

## Information provider

The V1 posture of the Hermes MCP surface toward Mac coding agents: supply cited information the local agent needs. Hermes does not author implementation plans, mutate worktrees, or open PRs for that agent.
_Avoid_: generate_plan / execute_plan / push_plan_pr as core V1 MCP tools; “Hermes plans or implements my ticket” as the default V1 story

## Coding-agent MCP jobs (V1)

The three jobs a Mac coding agent may call Hermes MCP for in V1: cross-repo retrieval (R), session/task brief (B), and external research (X). Tutor, personal Discord tasks, and operator/VM status are not part of this coding-agent MCP job set.
_Avoid_: packing plan/execute/push into this job set; treating Discord task capture as a Mac-agent MCP job

## Coding-agent MCP suite (V1)

Named consumer tools for the Mac coding agent: `library_search` (R), `session_brief` (B), `conduct_research` (X), `knowledge_catalog` (indexed repos + freshness in one response), `expand_citation`, and `impact_map`. Information-only; no plan/execute/push tools. No `agent_query` mega-router — the Mac agent calls named tools only. Per-tool invocation and MiniMax start-work contracts live in #49.
_Avoid_: raw git navigate/blame/diff as peer MCP tools; splitting catalog and freshness into two MCP tools; merging all six into one job-enum mega-tool; agent_query as the coding-agent entrypoint

## knowledge_catalog

The MCP tool that lists what the codebase knowledge layer can see. Caller input: no required params; optional `repos[]` filter. Response `data`: `{ repos: [{ owner_name, default_branch, last_sync_at, sync_sha, status, stale }] }`. One tool covers both inventory and trust signals. Code-only — no MiniMax involvement.
_Avoid_: separate list_indexed_repos and index_freshness tools in V1; requiring repo filters for every call; bulky per-repo index stats in the V1 contract; MiniMax health narratives on the catalog response

## library_search

The single consumer-facing MCP read tool over the shared codebase knowledge layer. Caller input: required `query`; optional `repos[]`, `revision`, `limit` (default small, e.g. 5). Response `data`: `{ summary_markdown, hits: [{ citation, snippet, score? }] }` plus top-level deduped `citations[]` in the MCP response envelope. Path/symbol navigation, history, and diffs stay as internal index capabilities behind that tool — they are not separate V1 MCP tools.
_Avoid_: split read suite (search / explain / navigate / history-diff) as peer MCP tools in V1; pointers-only answers with no snippets; always returning full hunks in search; synthesized vs hits_only modes on the V1 caller contract; hits-only with no summary_markdown

## expand_citation

The MCP tool that materializes a wider or full code hunk from a citation. Caller input: required citation tuple fields (`repo`, `revision`, `path`, `start_line`, `end_line`); optional `symbol`; optional `context_lines` (default e.g. 10) to widen the window. No MiniMax involvement — purely deterministic code fetch. No whole-file fetch or opaque citation ID.
_Avoid_: replacing library_search; exposing raw path browse as a general file API; opaque citation_id as the only input; whole-file dumps

## impact_map

The MCP tool that returns a ranked cross-repo blast radius of related files/symbols from the codebase index. Caller input is a discriminated union: `{ mode: "seed", repo, symbol? | path?, revision? }` or `{ mode: "intent", intent: string, repos?: string[] }`. Start-work: code resolves seed (or bounded intent→seed lookup), then deterministic fan-out; MiniMax only writes optional `summary_markdown` from supplied nodes. Response `data`: `{ seed, nodes: [{ citation, relation, score? }], summary_markdown? }` plus top-level `citations[]`.
_Avoid_: treating impact_map as generate_plan; NL intent as a substitute for an implementation plan artifact; flat optional fields with inferred mode; MiniMax-invented blast-radius edges

## Structured tool environment

The fixed schemas, prompts, and authority checks around each MCP tool that steer MiniMax-M3 toward reliable output. V1 prefers strong contracts and guided backends over free-form routing the model must invent mid-call.
_Avoid_: underspecified mega-prompts; relying on the model to invent tool steps without schema guidance

## library_search start-work

For `library_search`, Hermes runs deterministic retrieve/rank/dedupe in code, then MiniMax-M3 only writes `summary_markdown` grounded in the supplied hits. The model does not choose retrieval steps.
_Avoid_: letting MiniMax invent the retrieval plan; summarizing without hit grounding

## MCP response envelope

The common JSON shape returned by every V1 coding-agent MCP tool: structured fields such as `ok`, `tool`, `data`, optional `citations` / `warnings` / `errors`, with Markdown only inside string fields when prose is needed — not Markdown-first tool replies.
_Avoid_: Markdown-only tool responses; per-tool hybrid envelopes (JSON for some tools, essay for others)

## Citation tuple

The shared code-anchor object across coding-agent MCP tools: `repo`, `revision` (commit-ish), `path`, `start_line`, `end_line` (1-based inclusive), and optional `symbol`. Snippets are not required on the tuple; wider hunks come from `expand_citation`.
_Avoid_: URI-only citation strings as the sole contract; requiring `snippet` on every citation

## MCP failure policy

Shared outcome rules for coding-agent MCP tools: missing/unavailable index → hard fail (`ok: false`, typed error); stale index → soft warn and proceed; empty-but-valid result → `ok: true` with empty `data`.
_Avoid_: treating empty search hits as errors; treating all staleness as hard failure; returning partial data when the index is unavailable