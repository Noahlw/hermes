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

Durable Postgres store for Hermes itself: canonical records, audit/events, research evidence, persona/task scope metadata, session-brief pointers, structured digests/allowlists (not codebase chunks; not Honcho’s peer graph).
_Avoid_: storing full repo indexes here; peer-chat wiki as SoT; SQLite as the V1 Hermes canonical engine

## Codebase index database

Durable Postgres store (+ pgvector + FTS) for processed coding repositories: commit-addressable paths, symbols, chunks, lexical + semantic retrieval over the #40 knowledge layer. Read by all personas; writable only through controlled ingestion.
_Avoid_: persona-private notes; mixing with Hermes operational tables; Qdrant-as-sole code SoT

## Session brief

A compact, citation-backed sum-up Hermes returns at session start (or on demand) so callers spend fewer tokens rediscovering codebase/task context. Built from the codebase index database and task memory, not from peer-chat modeling alone.
_Avoid_: dumping full chat history; uncited “what I remember” narratives as the brief

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