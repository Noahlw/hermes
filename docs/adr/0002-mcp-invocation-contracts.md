# Per-tool MCP invocation contracts and MiniMax start-work pattern

All six V1 coding-agent MCP tools share a JSON envelope (`ok`, `tool`, `data`, `citations?`, `warnings?`, `errors?`), a common citation tuple (`repo`, `revision`, `path`, `start_line`, `end_line`, `symbol?`), and a split failure policy (unavailable → hard fail; stale → warn + proceed; empty → ok with empty `data`).

MiniMax-M3 is only used as a grounded narrator: deterministic code handles retrieval, ranking, and graph traversal; the model writes summaries and briefs constrained to the evidence supplied. Two tools (`knowledge_catalog`, `expand_citation`) never call MiniMax.

## Considered options

- MiniMax-driven retrieval + ranking (rejected: weak model invents wrong plans)
- Fully deterministic / no model involvement (rejected: too rigid for task-specific briefs and research)
- Hybrid with bounded model tool-use (accepted for `conduct_research` only — one follow-up fetch round)

## Consequences

- Implementation must build a deterministic retrieve/rank pipeline before any MiniMax integration
- `conduct_research` needs a bounded tool-use loop (one follow-up), not open-ended agent autonomy
- Response schemas are fixed contracts; callers can parse without inspecting prose
