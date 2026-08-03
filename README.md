# Hermes

Hermes is a personal V1 assistant stack: a **codebase knowledge layer**
(Postgres + pgvector + indexer), a **code-plan information provider**
(coding-agent MCP suite), and a **research agent** (`conduct_research`).
It ships **five personas** (Main Agent, Librarian, Researcher, Assistant,
Tutor) wired into hermes-agent's `pre_gateway_dispatch` hook. MiniMax-M3
is the only model provider. Three Discord bots (Assistant, Tutor, Main
Agent) listen on the Tailscale-internal home channel; Librarian and
Researcher are MCP-only. Zero public exposure.

**Install: [INSTALL.md](./INSTALL.md)** — the runbook, or `bash setup/install.sh` for the scripted phases.