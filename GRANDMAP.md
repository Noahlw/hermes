# Hermes Grand Map
> **Single canonical artifact** for the Hermes Agent deployment at `129.150.37.112`.
> Compiled from the wayfinder chart at https://github.com/Noahlw/hermes/issues/1.
> This is the **first compile pass** — most sections await ticket closure (D-013).
> Compiled: 2026-07-23 (chart-pass v1). Re-run T-024 (#25) to refresh.
---
## Destination
A production-grade **Nous Research `hermes-agent`** running on `129.150.37.112`, with: (1) a curated persona menu (incl. a `Librarian` persona), (2) a self-hosted persistent memory layer, (3) an internal **LLM wiki** system (cron-driven; clones default branches of 20–100 repos; embeds + indexes) — **deferred until core functionality lands** (D-010) — and (4) a **Tailscale-reachable MCP surface** that exposes *Hermes as a librarian* — so coding agents on the user's Mac and other PCs ask "how does X work in repo Y?" through Hermes, never against the wiki directly.
## Decisions so far (D-001 .. D-014)
Pulled verbatim from map #1 — each decision is one link-depth from a closed planning ticket.
- **D-001** — Claude-mem is abandoned; no history import. Wiki + memory carry cross-session context from now on.
- **D-002** — Memory is **self-hosted** on the VM.
- **D-003** — Personas are grilled in T-005, not pre-decided.
- **D-004** — Cross-PC transport is **Tailscale**.
- **D-005** — Cross-PC surface is **Hermes as librarian**, not raw wiki.
- **D-006** — `internal-wiki/` is **research input** only — sample for vocabulary/structure; don't inherit the project. Survives D-010 via T-017 (repurposed to glossary feeder).
- **D-007** — Destination is **wider** (cron ingestion + cross-PC librarian) on top of the original four pillars.
- **D-008** — Wiki scale is **medium** (20–100 repos, multi-language, single-VM with growth headroom).
- **D-009** — **T-001 is sequenced for end-of-chart.** Lane-A work (`lane:no-ssh`) runs in full first; Lane B (`lane:ssh-gated`) is held until the user rotates the SSH key by hand.
- **D-010** — **Wiki is deferred.** T-010 closed as not-planned. Wiki chain re-tickets when core Hermes + memory + librarian surface are functional end-to-end. The destination is unchanged; only the order of work has shifted.
- **D-011** — **Wiki-chain parking.** T-012..T-016 closed as not-planned-per-D-010. T-011 and T-017 repurposed (parking marker + glossary feeder). Re-ticket the wiki chain when D-010 lifts.
- **D-012** — **T-025 monthly recommender** — chart self-refreshes via a monthly `/research` subagent that produces 0+ new `phase:planning` tickets labeled `origin:auto-research`, `provenance:monthly-YYYY-MM`. User triages.
- **D-013** — **Planning → Spec → Implementation life-cycle.** Every ticket is `phase:planning`. Closing one = spec lives in the close comment. Orchestrator spawns a `phase:implementation` child whose body is verbatim spec; agent claims, executes, closes.
- **D-014** — **Five ops gaps added** as new Lane B tickets (T-019..T-023) — observability, librarian health, upgrade strategy, wiki backup (parked), token cost tracking.


## Provider

| Ticket | Status | Title | Link |
|---|---|---|---|
| T-006 | open | [T-006] LLM tier routing + provider YAML | https://github.com/Noahlw/hermes/issues/7 |

## Personas

| Ticket | Status | Title | Link |
|---|---|---|---|
| T-005 | open | [T-005] Persona menu grilling session | https://github.com/Noahlw/hermes/issues/6 |
| T-007 | open | [T-007] Persona YAMLs + persona-switch UX | https://github.com/Noahlw/hermes/issues/8 |

## Memory

| Ticket | Status | Title | Link |
|---|---|---|---|
| T-008 | open | [T-008] Memory backend research | https://github.com/Noahlw/hermes/issues/9 |
| T-009 | open | [T-009] Memory deployment + hardening | https://github.com/Noahlw/hermes/issues/10 |

## Network

| Ticket | Status | Title | Link |
|---|---|---|---|
| T-018 | open | [T-018] Tailscale bootstrap (VM + this Mac + other PC) | https://github.com/Noahlw/hermes/issues/19 |

## Observability

| Ticket | Status | Title | Link |
|---|---|---|---|
| T-019 | open | [T-019] Observability / heartbeat / status command | https://github.com/Noahlw/hermes/issues/20 |
| T-020 | open | [T-020] Librarian service health & auto-restart | https://github.com/Noahlw/hermes/issues/21 |
| T-023 | open | [T-023] Token cost tracking | https://github.com/Noahlw/hermes/issues/24 |

## Operations / Runbook

| Ticket | Status | Title | Link |
|---|---|---|---|
| T-021 | open | [T-021] Hermes upgrade strategy | https://github.com/Noahlw/hermes/issues/22 |

## Glossary

| Ticket | Status | Title | Link |
|---|---|---|---|
| T-017 | open (repurposed) | [T-017] Sample internal-wiki/ for prior art | https://github.com/Noahlw/hermes/issues/18 |
## Open tickets (current state)
19 open planning tickets. Lane A actionable now; Lane B behind T-001.

| # | T | Lane | Type | Title |
|---|---|---|---|---|
| #2 | [T-001] | Lane B | task | Compromise-response key rotation |
| #3 | [T-002] | Lane B | task | VM inventory + already-installed-Hermes assessment |
| #4 | [T-003] | Lane B | task | VM clean-up plan |
| #5 | [T-004] | Lane B | task | Hermes install or harden |
| #6 | [T-005] | Lane A | grilling | Persona menu grilling session |
| #7 | [T-006] | Lane A | research | LLM tier routing + provider YAML |
| #8 | [T-007] | Lane B | task | Persona YAMLs + persona-switch UX |
| #9 | [T-008] | Lane A | research | Memory backend research |
| #10 | [T-009] | Lane B | task | Memory deployment + hardening |
| #12 | [T-011] | Closed | task | Repo list for the wiki |
| #18 | [T-017] | Closed | research | Sample internal-wiki/ for prior art |
| #19 | [T-018] | Lane B | task | Tailscale bootstrap (VM + this Mac + other PC) |
| #20 | [T-019] | Lane B | task | Observability / heartbeat / status command |
| #21 | [T-020] | Lane B | task | Librarian service health & auto-restart |
| #22 | [T-021] | Lane B | task | Hermes upgrade strategy |
| #23 | [T-022] | Lane B | task | Wiki backup / restore target (parked pending D-010 lift) |
| #24 | [T-023] | Lane B | task | Token cost tracking |
| #25 | [T-024] | Lane A | task | Compile grand map from ticket outputs |
| #26 | [T-025] | Lane A | research | Monthly improvement recommender |

## Closed tickets (parked — wiki chain back-burnered per D-010 / D-011)
| # | ID | Status | Re-ticket trigger |
|---|---|---|---|
| #11 | T-010 | closed (D-010) | Wiki returns |
| #13 | T-012 | closed (D-011) | Wiki returns |
| #14 | T-013 | closed (D-011) | Wiki returns |
| #15 | T-014 | closed (D-011) | Wiki returns |
| #16 | T-015 | closed (D-011) | Wiki returns |
| #17 | T-016 | closed (D-011) | Wiki returns |

## Out of scope
- Multi-region / HA
- Air-gapped deployment
- Self-trained embeddings or LLMs (we consume, we don't ship)
- New desktop or mobile shells
- Public exposure of any service without auth
- Inheriting the `internal-wiki/` project as-is
- Training new embeddings on the user's repos (use Voyage/Cohere/etc.)

## Re-running this compile

Per T-024 (#25) ticket body, this artifact regenerates whenever:
- A new D-N is appended to the map
- A planning ticket closes (close comment is the spec)
- An implementation ticket closes (deliverable summary + artifact path)
- Quarterly cron (default) OR user invocation of `/compile-grand-map`

The next compile absorbs the latest state — concrete population of Provider/Personas/Memory/Network/Observability sections happens as Lane A agents close #6, #7, #9, #18.

## Glossary (pending T-017 closure)
_Vocabulary section populates when T-017 closes with the internal-wiki-concepts note._
