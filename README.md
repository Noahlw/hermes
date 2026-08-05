# Hermes

Installer playbook + extension layer for the **official Hermes Agent**
(NousResearch/hermes-agent), which is installed the official way
(`curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`).

The repo extends the official runtime with:

- **Five personas** (Main Agent, Librarian, Researcher, Assistant, Tutor)
  with hard contract gates — `hermes/personas/`, wired into upstream's
  `pre_gateway_dispatch` hook via `hermes/hermes_agent_plugin/`.
- **Three Discord bots** (Main Agent, Assistant, Tutor) as upstream profiles
  with isolated Honcho memory; Librarian/Researcher stay job-backed (MCP).
- **Codebase knowledge layer**: Postgres + pgvector indexer
  (`hermes/indexer/`), consumed through hermes as MCP tools / plugin tools.
- **Self-hosted memory infra**: Honcho API/deriver + Ollama local embeddings
  (D-C) — no training-on-prompt providers (IDX-1).
- MiniMax-M3 as the **only** LLM provider. Zero public exposure; Tailscale
  for all cross-PC traffic; MCP is the consumer surface.

**For a coding agent: read [AGENTS.md](./AGENTS.md) — the executable
install/verify/decommission runbook.** Humans: [INSTALL.md](./INSTALL.md).

Architecture decisions: [docs/adr/](./docs/adr/) (esp. ADR 0007 — the
official-installer pivot; ADRs 0001–0006 + CONTEXT.md document the V1 persona
contracts and target environment). The pre-pivot private runtime is archived
under [`archive/`](./archive/) — reference only.
