# Hermes Domain Glossary

## Persona

A distinct Hermes operating identity for a recurring kind of work. Each persona is an independently callable subagent with its own purpose, tools, authority, memory scope, and response contract. It is not merely a prompt variation.

The exact persona set and the boundaries between personas remain to be decided during the planning interview.

## Persona selection

Callers select a persona explicitly when they need specialized behavior. If no persona is selected, Hermes falls back to the Main Agent.

## Main Agent

The default Hermes operating identity used when a caller does not choose a specialized persona. It is a full general-purpose persona that can handle ordinary work itself and delegate when specialization is useful.

## Persona delegation

The Main Agent may delegate to specialized personas. A specialized persona may delegate only when its persona contract explicitly permits it; delegation is not an unrestricted peer-to-peer behavior.

## Persona memory

Each persona has isolated working memory for its own preferences, reasoning context, and operating history. The shared codebase knowledge layer is available to all personas. Cross-persona handoffs carry explicit task context and do not expose private persona memory by default.

## V1 persona set

V1 ships with a fixed, deliberate set of personas discovered during use-case research, plus the Main Agent. User-created personas are outside the V1 boundary.

`Librarian`, `Developer`, and `Researcher` are starting hypotheses, not commitments. Use-case research may confirm, split, merge, or replace them.

## Hermes V1 planning destination

This wayfinder map ends at an implementation-ready Hermes V1 specification and dependency-ordered execution plan. Deployment on the user's VM follows as implementation, not as part of the planning map.

Use-case research must actively discover additional ways Hermes fits the user's life beyond knowledge retrieval, code-plan implementation, and research. Those findings shape the fixed V1 persona set and MCP surface.

## Persona contract

A source-managed definition for one persona. It states the persona's purpose, allowed tools, authority limits, memory scope, delegation rules, response format, and acceptance scenarios. Each fixed V1 persona must have a contract.

## Persona authority boundary

A specialized persona must not silently act beyond its contract. When a request exceeds its authority, it returns an explicit out-of-scope result and may escalate to the Main Agent.

When a caller explicitly selects a specialist and that specialist cannot handle the request, escalation goes only to the Main Agent; Hermes does not silently switch to another specialist.

## MiniMax-only

Provider policy: Hermes may call MiniMax-M3 only. No OpenRouter, Codex, or DeepSeek fallback is permitted.

## Assistant channel

The end-user chat surface for the Assistant persona. In V1 this is Discord only: messages on the configured home channel from allowlisted users.
_Avoid_: Telegram, DM-only Assistant gateway, multi-channel fan-out

## Discord home channel

The single Discord channel Hermes monitors for Assistant note capture and task digests. Identified by `DISCORD_HOME_CHANNEL`. Messages outside this channel are ignored for V1 Assistant work.

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
_Avoid_: dumping full chat history; uncited “what I remember” narratives as the brief; requiring Honcho preferences to build the V1 brief

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

## Tailscale-internal surface

Services intentionally reachable on the Tailscale mesh (not the public internet). V1 accepts SSH, tailscaled, Hermes gateway, and Open WebUI on that mesh. AgentMemory ports are removal targets. Leftover listeners are cleanup debt, not a rewrite of the zero-public-exposure rule.

## Hybrid close

For use-case research tickets: close after the accepted spec is written **and** a short list of live VM hardening checks pass; remaining ops may follow as separate tickets.

## Portable restore

The ability to stand up Hermes on a new machine by cloning from GitHub and restoring durable databases from Google Drive backups, so a deleted VM is not a total loss. V1 backup set: Hermes Postgres, codebase-index Postgres, Honcho Postgres; secrets via a separate encrypted/offline path.
_Avoid_: treating the Oracle VM disk as the only copy of truth; Neo4j dumps as the recovery path; putting `.env`/tokens in the public repo or unencrypted Drive

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