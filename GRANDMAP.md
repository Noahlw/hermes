# Hermes Grand Map — v2

> Reality-anchored single canonical artifact for the Hermes Agent deployment at `129.150.37.112`.
> Anchored to the 2026-07-23 VM probe (`probe-artifacts/`).
> Compiled by T-NEW-09 (#35) on chart restart.

---

## Destination

A **production-grade Hermes Agent (v0.15.1 already installed)** at `129.150.37.112`, with: (1) the **5-step setup plan from `/home/ubuntu/.hermes/hermes-setup-plan.md` completed** (subagent fallback chain, token optimization, config polish, VM maintenance cron, coder profile brought up to spec); (2) the existing **triple-stack memory** (Qdrant + mem0 + agentmemory + Honcho) audited and consolidated per the user's choice; (3) a **persona menu** based on SOUL.md + the existing `default` and `coder` profiles; (4) a **token-cost ledger** integrated with the existing `kanban.db`; (5) **`hermes-status` heartbeat** + Tailscale-side Tailscale on remaining PCs; (6) **wiki + librarian surface** (deferred until memory + personas + observability are functional); (7) a **monthly recommendation cron** that catches up with the tech landscape.

## VM Snapshot (probe 2026-07-23)

| Item | Value |
|---|---|
| Host | `instance-20260511-1727` (Ubuntu 24.04.4 LTS, aarch64) |
| Resources | 4 CPU · 23 GiB RAM · 193 GB disk (105 GB free) |
| Tailscale IP | `100.79.87.93` |
| Hermes Agent | v0.15.1 (2026.5.29), Python 3.11.15, project at `/home/ubuntu/.hermes/hermes-agent/` |
| Memory stack | Qdrant (`qdrant_mem0`) + mem0 + agentmemory (port 8642) + Honcho (postgres+redis+api+deriver) |
| Other services | neo4j, ollama (11434), nginx, open-webui, honcho-self-hosted |
| Shell wrapping | `/usr/local/bin/hermes` shim → Docker container |
| Tailscale users | `noahklw119@` (this Linux); offline: `noahpc`, `node` (mac), `noahs-macbook-air` (this Mac, now online) |

## Decisions so far (D-001..D-017)

Pulled verbatim from map #27.

- **D-001** — Claude-mem is abandoned; no history import. Wiki + memory carry cross-session context from now on.

- **D-002** — Memory is **self-hosted** on the VM. Realized as **triple-stack**: Qdrant (`qdrant_mem0`), mem0 (`~/.hermes/mem0.json`), agentmemory (`agentmemory.service` port 8642), Honcho (`honcho-self-hosted` Docker stack with postgres+redis+api+deriver, peer `hermes` observing `ubuntu`).

- **D-003** — Personas are grilled, not pre-decided.

- **D-004** — Cross-PC transport is **Tailscale**. Realized: VM at `100.79.87.93` online; this Mac `noahs-macbook-air` at `100.104.102.94` brought back online 2026-07-23.

- **D-005** — Cross-PC surface is **Hermes as librarian**, not raw wiki.

- **D-006** — `internal-wiki/` is **research input** only. Adopted via T-017 (repurposed to grand-map glossary feeder).

- **D-007** — Destination scope is wider (cron + cross-PC + memory + observability).

- **D-008** — Wiki scale **medium** (20–100 repos).

- **D-009** — Lane discipline (lane:no-ssh vs lane:ssh-gated).

- **D-010** — **Wiki deferred** until core functionality lands. T-010 closed; T-012..T-016 closed as not-planned-per-D-010/D-011. Parked until core ships.

- **D-011** — Wiki-chain parking. T-011 and T-017 repurposed. T-022 wiki backup parked.

- **D-012** — T-025 monthly recommender — chart self-refreshes via monthly `/research`.

- **D-013** — Planning → Spec → Implementation life-cycle (`phase:planning`, `phase:implementation`, `phase:wrap-up`).

- **D-014** — Five ops-gap tickets added (T-019..T-023).

- **D-015** — **Probe-driven chart restart** (this map, 2026-07-23). The previous chart was anchored to a hypothetical `/opt/hermes/` layout; the v2 chart is anchored to the actual `/home/ubuntu/.hermes/` state captured in `probe-artifacts/`.

- **D-016** — **Leaked SSH RSA key accepted as-is** (security debt). User explicitly chose option (b) in the access plan; T-NEW-09 (re-rotation) is the load-bearing remediation ticket.

- **D-017** — **Provider is MiniMax-only**. No OpenRouter, no Codex fallback, no DeepSeek direct. T-NEW-01 (#37) closed as resolved per user directive. The 5-step setup plan's Step 1 fallback chain is superseded; only the MiniMax provider block + env var survive.


## T-NEW-03 (#29) Memory architecture

Pending T-NEW-03 close — audit/consolidate Qdrant+mem0+agentmemory+Honcho.

## T-NEW-04 (#30) Persona menu

Pending T-NEW-04 close — persona menu + SOUL.md + default/coder integration.

## T-NEW-05 (#31) Token-cost observability

Pending T-NEW-05 close — kanban.db + Honcho derived ledger.

## T-NEW-06 (#32) Observability + tailscale

Pending T-NEW-06 close — `hermes-status` heartbeat, Tailscale on remaining PCs.

## T-NEW-02 (#28) Five-step setup plan

Pending T-NEW-02 close — ship user's hermes-setup-plan.md Steps 1-5 to done.

## Wiki + Librarian (parked)

T-NEW-07 (#33): placeholder per D-010. Re-tickets when wiki returns.

## Monthly notes

T-NEW-08 (#34): monthly cron `~/.hermes/scripts/monthly-research.sh` — first run TBD.

## Open tickets (current state)

10 tickets open on the v2 chart:

| # | ID | Type | Lane | Title |
|---|---|---|---|---|
| #28 | T-NEW-02 | task | ssh-gated | [02] Ship the user's 5-step hermes-setup-plan.md t |
| #29 | T-NEW-03 | grilling | ssh-gated | [03] Audit / consolidate Qdrant + mem0 + agentmemo |
| #30 | T-NEW-04 | grilling | ssh-gated | [04] Persona menu — SOUL.md + default/coder profil |
| #31 | T-NEW-05 | task | ssh-gated | [05] Token-cost ledger derived from kanban.db + Ho |
| #32 | T-NEW-06 | task | ssh-gated | [06] hermes-status heartbeat + Tailscale on remain |
| #33 | T-NEW-07 | task | ssh-gated | [07] Wiki + librarian MCP chain (parked per D-010) |
| #34 | T-NEW-08 | task | no-ssh | [08] Monthly improvement recommender (realized as  |
| #35 | T-NEW-09 | task | no-ssh | [09] GRANDMAP.md v2 recompile (T-024 successor) |
| #36 | T-NEW-10 | task | ssh-gated | [10] Rotate leaked RSA SSH key — security debt |


## Closed tickets (parked / superseded)

| # | Status | Note |
|---|---|---|
| #1 | archive:v1-map | v1 chart superseded |
| #2-#26 | superseded | v1 tickets re-ticketed at #28-#37 |
| #37 | closed | T-NEW-01 — MiniMax-only provider decision (closed as resolved per D-017) |


## Out of scope

- Multi-region / HA / failover
- Air-gapped deployment
- Self-trained embeddings or LLMs (we consume, don't ship)
- New desktop or mobile shells
- Public exposure of any service without auth
- Wiki core / library runtime work — parked per D-010
- GitHub-side work (private repo upgrades, CI workflows)


## Re-running this compile

Per T-NEW-09 (#35): recompile whenever:
- A new D-N is appended to map #27
- A planning ticket closes (close-comment is the spec)
- An implementation ticket closes
- Quarterly cron (default) OR user invocation of `/compile-grand-map`
