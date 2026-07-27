# Coding-agent MCP is an information suite, not a planner/implementor

Hermes V1 exposes Tailscale MCP to Mac coding agents as six named information tools (`library_search`, `session_brief`, `conduct_research`, `knowledge_catalog`, `expand_citation`, `impact_map`). Callers get cited retrieval, briefs, research evidence, catalog/freshness, citation expansion, and blast-radius maps — not plan authorship, worktree mutation, or PR delivery. A single `agent_query` router and Discord/Tutor/operator tools stay off this server. Per-tool invocation schemas and MiniMax start-work guidance are deferred to #49.

## Considered options

- One mega-tool / free-form `agent_query` that routes internally
- Full remote implementor suite (`generate_plan` / `execute_plan` / `push_plan_pr`)
- Support role that still authors plans for the Mac agent to run
- Information-only named suite (accepted)

## Consequences

- The Mac coding agent owns planning and edits; Hermes is the remote knowledge/research layer
- `docs/use-case-specification.md` §5’s eight-tool draft (including plan/execute) is superseded for the coding-agent MCP consumer and needs a follow-up rewrite
- Persona contracts (#44) must not assume Developer MCP mutation tools on this surface
