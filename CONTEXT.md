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

The set of services that persist and retrieve persona/shared knowledge. Candidates currently observed on the VM include Qdrant, mem0, Honcho, and neo4j. Which (if any) survive is decided by research ticket #41, not by the use-case spec.
_Avoid_: treating Ollama as a memory service; treating agentmemory as in-scope for V1 (it is being uninstalled)

## Local inference

On-VM model serving used for embeddings or generation (today: Ollama). Distinct from the memory stack.

## Tailscale-internal surface

Services intentionally reachable on the Tailscale mesh (not the public internet). V1 accepts SSH, tailscaled, Hermes gateway, and Open WebUI on that mesh. AgentMemory ports are removal targets. Leftover listeners are cleanup debt, not a rewrite of the zero-public-exposure rule.
