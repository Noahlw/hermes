---
status: accepted
---

# ADR 0007 — Official Hermes Agent runtime pivot (repo becomes installer + extensions)

The #76 roadmap built a private gateway runtime (`hermes_agent/`, D-B fork 2,
ADR 0004 amendment 2026-08-04) behind this repo's own install contract
(ADR 0005). Grilling session 2026-08-05 (Q1–Q8) reversed that: the runtime is
the **official Hermes Agent** (NousResearch/hermes-agent), installed **the
official way**, and this repo becomes its **installer playbook + extension
layer**.

## Decision

1. **Runtime = NousResearch/hermes-agent (official), installed officially.**
   Canonical install: `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`
   → `~/.hermes/hermes-agent` (code + venv), `~/.local/bin/hermes` (launcher),
   `hermes` / `hermes-agent` / `hermes-acp` console scripts. The repo ships no
   runtime code and no bespoke runtime installers.
2. **This repo = agent-readable playbook + extensions.** `AGENTS.md` at the
   repo root is the step-by-step instruction a coding agent follows to install
   the official runtime, configure it (MiniMax-M3 provider, profiles, Discord
   bots, self-hosted Honcho memory, indexer MCP), apply the extension layer,
   and verify. `INSTALL.md` summarizes for humans and points at `AGENTS.md`.
3. **Extension layer (what survives / is ported):**
   - `hermes/personas/` — contract gate + adapters + contracts (policy core,
     hermes-agent-agnostic) — **kept**
   - `hermes/hermes_agent_plugin/` — `pre_gateway_dispatch` plugin adapter —
     **kept**, wired via `~/.hermes/plugins/noahlw/` shim (official plugin
     discovery: drop `plugin.yaml` + Python into `~/.hermes/plugins/<name>/`)
   - `hermes/indexer/` + `hermes/digest/` + `hermes/profiles/` — **kept**;
     the indexer's knowledge surface (`library_search`, `session_brief`,
     `knowledge_catalog`, `expand_citation`, `impact_map` — ported from
     `archive/hermes_agent/mcp_server.py`, whose only archived deps were
     `hermes_agent.llm`/`hermes_agent.config`, replaced by upstream's own
     model + plugin config) is registered as upstream `mcp_servers.*` /
     plugin tools — upstream is the *client*, this repo serves; digest
     becomes a skill; job schedules port to upstream scheduling or
     systemd timers
   - `setup/ollama/` + `setup/honcho/` — **kept** as memory-infra
     provisioning (self-hosted Honcho + Ollama embeddings, D-C); upstream's
     Honcho memory provider points `baseUrl` at the self-hosted API
4. **Archived (git-reverse, history kept, no rewrite):** `hermes_agent/`,
   `tests/` (private-runtime tests), `cron/` (private scheduler),
   `setup/install.sh`, `setup/gateway.sh`, `setup/systemd/`,
   `setup/honcho-workspaces.py`, `hermes/honcho/` (isolation — replaced by
   upstream per-profile Honcho host blocks), `db/hermes/` (gateway DB
   schema). All → `archive/`.
5. **Persona roster unchanged** (ADR 0003): Main Agent, Librarian, Researcher,
   Assistant, Tutor. Main Agent / Assistant / Tutor = three upstream **profiles**
   with own Discord bot tokens + own Honcho host blocks
   (`hermes_<profile>`), matching CONTEXT.md "isolated working memory".
   Librarian / Researcher stay job-backed contracts enforced by the plugin
   gate on MCP jobs.
6. **VM (Oracle Ampere A1, Ubuntu 24.04 aarch64, host `hermes`) — staged
   swap (Q4/Q7):** install official runtime **alongside** the private stack;
   run the 7-check verification gate; only then stop+disable
   `hermes-gateway.service` + private cron scheduler, back up and drop the
   gateway Postgres DB (operator approval for the drop). **Keep**:
   honcho-api + honcho-deriver + ollama (memory/embedding infra), codebase
   index + indexer + its MCP server (now consumed by upstream via
   `mcp_servers`), systemd timers for jobs upstream cannot schedule.
7. **Posture preserved:** MiniMax-M3 only (D-D); Tailscale-only / zero public
   exposure (D3); MCP = consumer surface; no-training/no-retention providers
   (IDX-1); no force-push; reviewer gates on install-contract/ADR/PR changes.

## Considered options

- **Keep private runtime, wrap it in an official-style installer** — rejected
  (Q1): the user wants the official product; `hermes` must work exactly as
  upstream ships it; the repo's original design (README v1) was already a
  companion to hermes-agent, not a runtime.
- **Adopt upstream installer but keep private gateway running indefinitely** —
  rejected (Q4/Q7): staged swap with verification, then decommission; two
  runtimes = confusion (Q1 option 3 rejected for the same reason).
- **Hard-purge private code (force-reset)** — rejected (Q2): git-reverse via
  `archive/` keeps history and recoverability; the 411-test suite and gateway
  code remain inspectable as a reference for the port.

## Consequences

- `hermes` works on the VM again, as upstream ships it (root cause of #62:
  repo shipped no `hermes` command; nothing installed the official runtime).
- PRs/commits before this ADR remain in history; `archive/` documents the
  superseded runtime rather than deleting evidence.
- The 7-check gate (Q8) is the definition of "verified": doctor clean,
  MiniMax-M3 answers, all three Discord bots reply, `library_search` callable
  from inside hermes with citations, Honcho memory lands, digest fires, and
  no public listeners.
- Upstream moves fast (v0.20.x); the plugin adapter is pinned to the current
  `pre_gateway_dispatch` contract (action dicts `skip`/`rewrite`/`allow`).
  The playbook instructs agents to re-check the hook contract against the
  installed upstream version.
- Codebase knowledge layer (indexer, digests, profiles, contracts) is now
  upstream's data + policy; duplication with upstream natives (skills, cron,
  providers) is resolved by porting, not by maintaining two implementations.