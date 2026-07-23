# Hermes

This repo is the **wayfinder chart hub** for the Hermes Agent deployment on the Oracle VM at `129.150.37.112`. The chart of record lives on the GitHub issue tracker; this repo carries point-in-time artifacts the chart needs.

## Where the chart lives

The **Wayfinder Map** is [issue #1](https://github.com/Noahlw/hermes/issues/1).

Children are issues [#2](https://github.com/Noahlw/hermes/issues/2)–[#26](https://github.com/Noahlw/hermes/issues/26). 20 are open; 6 are closed (parked behind D-010 / D-011 wiki deferral).

Block / frontier queries:

```bash
# Actionable now (Lane A):
gh issue list --repo Noahlw/hermes --state open --label 'lane:no-ssh' \
  | jq '.[] | select(.blockedBy.nodes | length == 0) | select(.assignees | length == 0) | {n: .number, t: .title}'

# Held behind T-001 (Lane B):
gh issue list --repo Noahlw/hermes --state open --label 'lane:ssh-gated' \
  | jq '.[] | {n: .number, t: .title}'

# Wiki-deferred parking:
gh issue list --repo Noahlw/hermes --state open --label 'phase:waiting-wiki-lift'

# Wrap-up + recurring:
gh issue list --repo Noahlw/hermes --label 'phase:wrap-up,recurring:monthly'
```

## State of the map

| Decision | Summary |
|---|---|
| **D-001..D-007** | Foundational preferences (claude-mem abandoned, self-host memory, personas grilled, Tailscale, librarian surface, internal-wiki sampling, wider destination) |
| **D-008** | Wiki scale = medium (20–100 repos) |
| **D-009** | T-001 sequenced for end-of-chart (Lane discipline) |
| **D-010** | Wiki deferred |
| **D-011** | Wiki-chain parking: T-012..T-016 closed as not-planned-per-D-010 |
| **D-012** | T-025 monthly recommender (chart self-refreshes) |
| **D-013** | Planning → Spec → Implementation life-cycle (`phase:planning`, `phase:implementation`, `phase:wrap-up`) |
| **D-014** | 5 ops-gap tickets added: T-019..T-023 |

## Front-tier ticket table (every ticket's role in the grand map)

### Lane A — actionable now

| Issue | ID | Type | Phase | Output → Grand-map section |
|---|---|---|---|---|
| #6 | T-005 | grilling | planning | Persona menu → **Personas** |
| #7 | T-006 | research | planning | Provider YAML → **Provider** |
| #9 | T-008 | research | planning | Memory backend pick → **Memory** |
| #12 | T-011 | task (parked) | planning + waiting-wiki-lift | (placeholder) |
| #18 | T-017 | research (repurposed) | planning + waiting-wiki-lift | Glossary → **Glossary** |
| #25 | T-024 | task | **wrap-up** | `GRANDMAP.md` compilation |
| #26 | T-025 | research | **recurring:monthly** | Monthly research → new tickets |

### Lane B — sequenced for end-of-chart, behind T-001

| Issue | ID | Type | Phase | Output → Grand-map section |
|---|---|---|---|---|
| #2 | T-001 | task (HITL) | planning | ed25519 key → **Operations / Security** |
| #3 | T-002 | task | planning | VM inventory → **Operations / Current state** |
| #4 | T-003 | task | planning | Cleanup recipe → **Operations** |
| #5 | T-004 | task | planning | Hermes install → **Operations / Install** |
| #8 | T-007 | task | planning | Persona YAMLs → **Personas** |
| #10 | T-009 | task | planning | Memory deploy → **Memory** |
| #19 | T-018 | task (HITL) | planning | Tailscale bootstrap → **Network** |
| #20 | T-019 | task | planning | `hermes-status` + heartbeat → **Observability** |
| #21 | T-020 | task | planning | systemd watchdog → **Observability** |
| #22 | T-021 | task | planning | Upgrade strategy → **Operations** |
| #23 | T-022 | task | planning + waiting-wiki-lift | Wiki backup (parked) |
| #24 | T-023 | task | planning | Token cost tracking → **Operations / Cost** |

### Closed (parked behind D-010 / D-011)

#11 T-010 (D-010), #13 T-012, #14 T-013, #15 T-014, #16 T-015, #17 T-016 — re-ticket alongside wiki chain when D-010 lifts.

## How the chart self-organizes (D-013 life-cycle)

1. **Open** — ticket born as `phase:planning` child of map #1.
2. **Claimed** — assignee self-assigns (`gh issue edit N --add-assignee @me`).
3. **Worked** — assignee does the decision / research / grilling / task.
4. **Closed** — close-comment is the **spec** (must contain `## Rationale`, `## Acceptance`, `## Hand-off`).
5. **Spawned** — orchestrator (or user) creates a `phase:implementation` child whose body = verbatim spec.
6. **Done** — impl ticket closes with deliverable summary + path-to-artifact. Planning ticket stays closed; `phase:implementation` is the work plan.

Reaper: idle `phase:implementation` tickets are nudged at +7 days, closed-no-progress at +14 days.

## What this repo will hold later

Artifacts produced by ticket resolution land here, not pasted into issue bodies:

- `GRANDMAP.md` — single canonical document, compiled by T-024 (issue #25)
- `adr/` — architecture decision records (0001 onward)
- `vm/` — VM inventory reports, install logs, cleanup recipes (post-T-001)
- `personas/` — final persona YAMLs (canonical copies) — post-T-007
- `wiki-mcp/` — `CONTRACT.md`, `FIRST-CONNECTION.md`, schema files (re-ticketed on D-010 lift)
- `runbook/` — ops runbook drafts (final lands on the VM at `/opt/hermes/RUNBOOK.md`)

## Standing preferences (locked on the map)

- LLM frontier: `MiniMax-M3` (per T-006 spec)
- Self-hosted memory (per T-008 spec)
- Cross-PC transport: Tailscale; no public exposure of the librarian MCP
- All VM state under `/opt/hermes/{hermes,wiki,memories,backups,tailscale,run}`
- Wiki ingestion (when active): VM-side clones of `default` branches, no GitHub API rate limits
- API keys: env-var only (`HERMES_MM_KEY`); rotation quarterly or on personnel change

## Open questions (tracked on map #1 §Open questions)

1. `ready-for-agent` semantic — rename to `claim:available` or document dual use?
2. GRANDMAP.md at repo root vs `docs/grandmap.md`?
3. T-024 cadence — quarterly default OK?
4. T-018 user-driven install counts as planning — confirm
