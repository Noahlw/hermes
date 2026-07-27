# V1 persona roster: five contracts, three Discord bots, two job-backed MCP personas

Hermes V1 ships **Main Agent**, **Librarian**, **Researcher**, **Assistant**, and **Tutor**. **Developer** is out of V1 while the coding-agent MCP stays information-only (#42). Discord reaches personas by **@-mentioning a dedicated bot** on one shared home channel: Assistant, Tutor, and Main Agent (super-set: Assistant∪Tutor∪ops). Librarian and Researcher have **no** Discord bot; their contracts attach to MCP jobs (`library_search` / `session_brief` / `knowledge_catalog` / `expand_citation` / `impact_map` vs `conduct_research`), callable by any authorized Tailscale MCP consumer. Discord specialists that are out of scope **refuse + hint** only; MCP job-backed OOS returns a typed envelope and may leave an operator-visible Main Agent note when systemic. Each persona has isolated Honcho working memory; `manage_tasks` is Discord-only.

## Considered options

- Keep #39’s six-persona roster including Developer with plan/execute tools (rejected: superseded by #42)
- One Discord bot with intent/prefix routing (rejected: weak for MiniMax; softer authority boundaries)
- Five Discord bots including Librarian/Researcher (rejected: redundant with MCP; confuses job-backed model)
- Main Agent Discord as ops-only or ops+read (rejected: user chose super-set escape hatch)
- Auto-handoff from Assistant/Tutor to Main Agent on OOS (rejected: erases bot discipline)

## Consequences

- `docs/use-case-specification.md` §4–5 must be rewritten to match this roster and surfaces
- Implementation needs three Discord app tokens/listeners and persona contract sources; coding-agent MCP remains persona-agnostic
- Main Agent super-set authority must not share Assistant/Tutor Honcho peers
