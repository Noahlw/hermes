# Hermes V1 — Planner Handoff

> For the next planner. Full rebuild. Ignore all previous ticket ordering and chart structure.

## What Hermes is

Hermes does **three things:**

1. **Token-saving knowledge layer** — MCP tools for coding agents. Answers "how does X work in repo Y?" from an indexed wiki of 20–100 GitHub repos.
2. **Code plan implementor** — Not just retrieval. Hermes can generate and execute implementation plans against codebases.
3. **Research agent** — Can do background research, fact-gathering, and return structured findings.
4. **Other use cases TBD** — The planner must grill the user to discover additional ways Hermes fits into their life beyond what's already listed.

## Non-negotiables

- **MiniMax-M3 only.** No fallback chain, no OpenRouter, no DeepSeek, no Codex.
- **Self-hosted** on the VM at `/home/ubuntu/.hermes/`.
- **Tailscale** for all cross-PC traffic. Zero public exposure.
- **MCP tool surface** — coding agents and other consumers call Hermes as an MCP server, never touch repos or DBs directly.
- **General-purpose codebase wiki** — repos are GitHub-sourced, but no need to specify which projects now.

## Current VM state

- Hermes Agent v0.15.1 via Docker Compose
- Triple-stack memory running: Qdrant + mem0 + agentmemory + Honcho
- Tailscale up (VM: 100.79.87.93, Mac: 100.104.102.94)
- User-authored 5-step setup plan at `/home/ubuntu/.hermes/hermes-setup-plan.md`

---

## Tickets to create (order matters)

### 1. Use-case research & grilling
**What:** Research what the user will actually use Hermes for.
**Includes:**
- Map query patterns from real coding sessions (what do coding agents ask?)
- Define the code-plan-implementor workflow — what does "implement a plan" mean to Hermes?
- Define the research-agent workflow — what kind of research, what format, what sources?
- **Grill the user** to discover additional use cases not yet mentioned. Hermes is meant to fit into their life beyond just codebase Q&A. What else?

**Outputs:** list of use cases, query/command types per use case, what kind of response each needs.
**Why first:** Feeds persona design, MCP tool surface, indexing strategy, and implementation workflow. Everything depends on knowing how Hermes gets used.

### 2–5. These can run in parallel after ticket 1:
- **Codebase indexing strategy** — Compare approaches for indexing 20–100 GitHub repos (clone+embed vs. live RAG vs. other). Must support both retrieval and plan-implementation use cases.
- **Memory system evaluation** — Compare Honcho (already running) vs. newer alternatives (mem0 v2, Letta, LangMem, etc.) specifically for librarian/retrieval use. Not conversational memory — what should Hermes remember?
- **MCP tool surface design** — What tools does Hermes expose? Single `library_search()` or a suite (search, explain, list files, diff history, generate plan, research)?
- **Embedding model research** — User handles this themselves. Needs a prompt to research Voyage vs. Cohere vs. OpenAI vs. open-weight (Ollama) for code embedding. User returns a detailed report.

### 6. Persona grill
**What:** Based on use-case research (#1), grill what personas make sense. May not be the original Librarian/Developer/Student split from v1.
**Deferred:** Cannot be designed until you know what Hermes actually does.

### Deferred (ticket, but no urgency)
- **Monitoring / health checks** — `hermes-status` heartbeat, status command. Ticket exists, just not sequenced.
- **SSH key rotation** — Leaked RSA key still on VM. Rotate after core is functional.

---

## Not in scope for V1

- Cloud/remote memory (must be self-hosted)
- Public exposure of any service
- Multi-region / HA
- New desktop or mobile shells
- Defining "V1 done" — figure that out after research tickets land
