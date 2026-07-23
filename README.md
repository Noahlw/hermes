# Hermes

This repo is the **wayfinder chart hub v2** for the Hermes Agent deployment on the Oracle VM at `129.150.37.112`. The chart of record lives on the GitHub issue tracker; this repo carries the probe artifacts that drove v2 + the canonical `GRANDMAP.md`.

## Where the chart lives

The **Wayfinder Map v2** is [issue #27](https://github.com/Noahlw/hermes/issues/27) — probe-anchored, replaces [the v1 map #1](https://github.com/Noahlw/hermes/issues/1) (archived).

Children are issues [#28](https://github.com/Noahlw/hermes/issues/28) – [#37](https://github.com/Noahlw/hermes/issues/37). 11 are open; v1's 26 issues are closed (re-ticketed at the children).

## Chart state (v2 — 2026-07-23)

| Issue | T | Type | Lane | Summary |
|---|---|---|---|---|
| #27 | (map) | map | — | Probe-anchored v2 chart |
| #28 | T-NEW-02 | task | ssh-gated | Ship user's 5-step `hermes-setup-plan.md` to done |
| #29 | T-NEW-03 | grilling | ssh-gated | Audit / consolidate Qdrant+mem0+agentmemory+Honcho |
| #30 | T-NEW-04 | grilling | ssh-gated | Persona menu (SOUL.md + default/coder) |
| #31 | T-NEW-05 | task | ssh-gated | Token-cost ledger from `kanban.db` + Honcho |
| #32 | T-NEW-06 | task | ssh-gated | `hermes-status` heartbeat + Tailscale on remaining PCs |
| #33 | T-NEW-07 | task | ssh-gated | Wiki + librarian MCP chain (parked per D-010) |
| #34 | T-NEW-08 | task | no-ssh | Monthly improvement recommender (Hermes cron) |
| #35 | T-NEW-09 | task | no-ssh | GRANDMAP.md v2 recompile (T-024 successor) |
| #36 | T-NEW-10 | task | ssh-gated | Rotate leaked RSA SSH key — security debt |
| #37 | T-NEW-01 | task | ssh-gated | Verify provider/delegation against plan Step 1 |

## What changed from v1

The v1 chart was drafted from a hypothetical `/opt/hermes/` layout. On 2026-07-23 the actual VM was probed via SSH (using the leaked RSA key — see T-NEW-10):

- Hermes Agent **v0.15.1 already installed** at `/home/ubuntu/.hermes/` (NOT `/opt/hermes/`)
- Memory stack **already deployed**: Qdrant (`qdrant_mem0` container) + mem0 + agentmemory (systemd) + Honcho (postgres+redis+api+deriver) + neo4j + ollama
- Tailscale **running on VM** at `100.79.87.93`; this Mac `noahs-macbook-air` brought back online 20h after probe
- A 5-step `hermes-setup-plan.md` exists and is in-flight

Probe artifacts under `probe-artifacts/`:

- `probe-a.txt` — initial system + `/opt` listing
- `probe-b.txt` — runtime tools, docker state, services, tailscale, ports, crons
- `probe-c.txt` — user dirs, compose files, agentmemory systemd
- `probe-d.txt` — Hermes directories and config state
- `hermes-setup-plan.md` — the user's 5-step plan verbatim
- `probe-summary.md` — digest

## Decisions carried over

D-001..D-014 from the v1 chart are preserved as institutional preferences in the v2 map's *Decisions so far*. D-015 (probe-driven chart restart) and D-016 (leaked SSH key accepted as-is, security debt) are new.

## Standing preferences (unchanged from v1)

- LLM frontier via OpenRouter + Codex 5.2 + DeepSeek direct fallback chain (per `hermes-setup-plan.md` Step 1)
- Self-host memory on the VM (already shipped: triple-stack)
- Tailscale for all cross-PC; no public exposure
- All state under `/home/ubuntu/.hermes/`
- API keys in `~/.hermes/.env` (mode 600), env-var only; rotate quarterly or on personnel change
- Hermes via Docker Compose

## How to use this chart

Same D-013 life-cycle as v1: planning → close with spec → spawn implementation child. Front-tier queries:

```bash
# Actionable now (Lane A):
gh issue list --repo Noahlw/hermes --state open --label 'lane:no-ssh'

# Held behind T-001 (Lane B):
gh issue list --repo Noahlw/hermes --state open --label 'lane:ssh-gated'

# Wiki-deferred parking:
gh issue list --repo Noahlw/hermes --state open --label 'phase:waiting-wiki-lift'

# Wrap-up + recurring:
gh issue list --repo Noahlw/hermes --label 'phase:wrap-up,recurring:monthly'
```

## What this repo holds

- `GRANDMAP.md` — v2 canonical artifact (compiled by T-NEW-09 #35)
- `probe-artifacts/` — raw VM probe
- `AGENT-PROMPTS.md` — copy-pasteable prompts for agent picks (carried from v1)
- `README.md` — this file
