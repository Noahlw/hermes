# Hermes

This repo is the **wayfinder chart hub** for the Hermes Agent deployment on the Oracle VM at `129.150.37.112`. The chart of record lives on the GitHub issue tracker; this repo carries point-in-time artifacts the chart needs.

## Where the chart lives

The **Wayfinder Map** is [issue #1](https://github.com/Noahlw/hermes/issues/1) on this repo's GitHub Issues.

The 18 child tickets are issues [#2](https://github.com/Noahlw/hermes/issues/2)–[#19](https://github.com/Noahlw/hermes/issues/19). Blocking relationships are wired natively on GitHub; the frontier is "open + unblocked + unclaimed children of #1."

The single ticket-resolution command to view the frontier:

```
gh issue list --repo Noahlw/hermes --state open \
  --label 'wayfinder:research,wayfinder:prototype,wayfinder:grilling,wayfinder:task' \
  --json number,title,labels,blockedBy,assignees \
  | jq '.[] | select(.blockedBy.nodes | length == 0) | select(.assignees | length == 0)'
```

## State of the map (last chart pass — D-009 lane split)

Tickets are labelled `lane:no-ssh` (Lane A — actionable now) or `lane:ssh-gated` (Lane B — held until T-001 runs at end-of-chart).

### Lane A (no SSH — actionable now)

| ID | Ticket | Type | Blocked-by |
|---|---|---|---|
| #6 [T-005] | Persona menu grilling session | grilling | — |
| #7 [T-006] | LLM tier routing + provider YAML | research | — |
| #9 [T-008] | Memory backend research | research | — |
| #12 [T-011] | Repo list for the wiki | task | — |
| #18 [T-017] | Sample internal-wiki/ for prior art | research | — |

> T-010 (#11) was **closed as not-planned per D-010** — wiki architecture research is deferred until core functionality lands. T-011 (repo list) remains useful for re-ticketing wiki work later.

### Lane B (SSH-gated — sequenced for end-of-chart, behind T-001)

| ID | Ticket | Type | Blocked-by |
|---|---|---|---|
| #2 [T-001] | Compromise-response key rotation | task | — (user-owned, sequenced last) |
| #3 [T-002] | VM inventory + already-installed-Hermes assessment | task | T-001 |
| #4 [T-003] | VM clean-up plan | task | T-002 |
| #5 [T-004] | Hermes install or harden | task | T-003 |
| #8 [T-007] | Persona YAMLs + persona-switch UX | task | T-005, T-006 |
| #10 [T-009] | Memory deployment + hardening | task | T-003, T-008 |
| #13 [T-012] | Active ingestion scheduler | grilling | T-010, T-011 |
| #14 [T-013] | Wiki core + librarian surface deploy | task | T-007, T-009, T-010, T-011, T-012 |
| #15 [T-014] | Librarian contract + auth | grilling | T-013 |
| #16 [T-015] | End-to-end smoke (cross-PC) | task | T-013, T-014 |
| #17 [T-016] | Operations runbook | task | T-015 |
| #19 [T-018] | Tailscale bootstrap (VM + this Mac + other PC) | task | T-001 |

**Workflow:**

1. Run **all of Lane A** in parallel using Codex/agent tools (research tickets) and the user (T-005, T-011).
2. When Lane A is exhausted or sufficiently progressed, the user runs **T-001** (key rotation) by hand.
3. With T-001 closed, T-002 and T-018 unlock, and Lane B proceeds in dependency order.
4. **Wiki work (T-010 and downstream T-012/T-013/T-014/T-015/T-016) is deferred (D-010)** — re-ticket when core functionality is functional end-to-end.

Final frontier query:

```
gh issue list --repo Noahlw/hermes --state open \
  --label 'lane:no-ssh' \
  --json number,title,labels,blockedBy,assignees \
  | jq '.[] | select(.blockedBy.nodes | length == 0) | select(.assignees | length == 0)'
```

## Convention for ticket claims

- **Claim** = assign yourself (`gh issue edit N --add-assignee @me`).
- **Resolve** = post the answer as a comment, then close (`gh issue close N --comment "Resolved: ..."`).
- **Surfaced tickets** = create as child issues of #1 with `parent:1` and wire blocking via `gh issue edit --add-blocked-by` or `--add-blocking`.
- **Out-of-scope decisions** = close the ticket; the map's *Out of scope* section grows one line, the *Decisions so far* does **not**.

## What this repo will hold later

Artifacts produced by ticket resolution land here, not pasted into issue bodies:

- `vm/` — VM inventory reports, install logs, cleanup recipes
- `personas/` — final persona YAMLs (canonical copies)
- `wiki-mcp/` — `CONTRACT.md`, `FIRST-CONNECTION.md`, schema files
- `runbook/` — ops runbook drafts (final lands on the VM at `/opt/hermes/RUNBOOK.md`)
- `adr/` — architecture decision records landed as part of resolution

## Standing preferences (locked on the map)

- LLM tiering: `MiniMax-M3` is the frontier and used for most work; cheaper model for narrow high-volume tasks only
- VM: `ubuntu@129.150.37.112`; SSH via the rotated `ed25519` key (never paste private keys in chat)
- Cross-PC transport: **Tailscale**; no public exposure of the librarian MCP endpoint
- All VM state under `/opt/hermes/{hermes,wiki,memories,backups,tailscale,run}`
- Wiki ingestion: VM-side clones of `default` branches, no GitHub API rate limits
