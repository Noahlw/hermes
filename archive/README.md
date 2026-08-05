# archive/ — superseded private runtime (reference only)

ADR 0007 (2026-08-05) pivoted this repo to the **official Hermes Agent**
(NousResearch/hermes-agent) as the runtime, installed the official way. The
items here are the bespoke private runtime and its tooling, moved verbatim
(git mv — history preserved, nothing rewritten) for reference. **Do not
resurrect, port, or extend anything here**; the extension layer lives in
`hermes/` and the runbook in `AGENTS.md`.

| Path | What it was | Superseded by |
|---|---|---|
| `hermes_agent/` | private gateway runtime (main, mcp_server, cron_scheduler, discord_adapter, honcho_client, llm, config) | official hermes-agent gateway (`hermes gateway`) |
| `tests/` | 411-test suite for the private runtime + indexer integration | VM 7-check gate (AGENTS.md Step 4) — no in-repo suite was ported (Q8) |
| `cron/` (`jobs.json`) | private scheduler job set | upstream scheduling / systemd timers (AGENTS.md Step 2f) |
| `setup/install.sh`, `setup/gateway.sh`, `setup/systemd/` | bespoke install contract (ADR 0005) | official installer `curl -fsSL https://hermes-agent.nousresearch.com/install.sh \| bash` |
| `setup/honcho-workspaces.py` | private Honcho workspace provisioning | upstream Honcho host blocks (`~/.hermes/honcho.json`) |
| `hermes/honcho/` (`isolation.py`) | private memory isolation | upstream per-profile Honcho peers |
| `db/hermes/` | gateway Postgres schema | (decommissioned with the private stack) |
| `.env.example` | private runtime env reference | new `.env.example` at repo root |

Kept in `hermes/` (live extension layer): `personas/` (contract gate),
`hermes_agent_plugin/` (upstream `pre_gateway_dispatch` adapter), `indexer/`,
`digest/`, `profiles/`. Kept in `setup/`: `ollama/`, `honcho/`, `honcho.sh`
(memory infra provisioning).

Decisions: ADR 0007, ADR 0003 (persona roster), ADR 0006 (target env),
CONTEXT.md (persona contracts).