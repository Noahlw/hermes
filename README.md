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

## State of the map (last chart pass)

| ID | Ticket | Type | Blocked-by |
|---|---|---|---|
| #2 [T-001] | Compromise-response key rotation | task | — (frontier, user-owned) |
| #3 [T-002] | VM inventory + already-installed-Hermes assessment | task | T-001 |
| #4 [T-003] | VM clean-up plan | task | T-002 |
| #5 [T-004] | Hermes install or harden | task | T-003 |
| #6 [T-005] | Persona menu grilling session | grilling | — (frontier) |
| #7 [T-006] | LLM tier routing + provider YAML | research | — (frontier) |
| #8 [T-007] | Persona YAMLs + persona-switch UX | task | T-005, T-006 |
| #9 [T-008] | Memory backend research | research | — (frontier) |
| #10 [T-009] | Memory deployment + hardening | task | T-003, T-008 |
| #11 [T-010] | Wiki + librarian-surface architecture research | research | — (frontier) |
| #12 [T-011] | Repo list for the wiki | task | — (frontier) |
| #13 [T-012] | Active ingestion scheduler | grilling | T-010, T-011 |
| #14 [T-013] | Wiki core + librarian surface deploy | task | T-007, T-009, T-010, T-011, T-012 |
| #15 [T-014] | Librarian contract + auth | grilling | T-013 |
| #16 [T-015] | End-to-end smoke (cross-PC) | task | T-013, T-014 |
| #17 [T-016] | Operations runbook | task | T-015 |
| #18 [T-017] | Sample internal-wiki/ for prior art | research | — (frontier) |
| #19 [T-018] | Tailscale bootstrap (VM + this Mac + other PC) | task | — (frontier) |

After T-001 closes, **8 frontier tickets** open simultaneously: T-002, T-005, T-006, T-008, T-010, T-011, T-017, T-018. Of these, the three `research` tickets (T-006, T-008, T-010) and T-017 are best resolved by **agent** sessions; T-002 / T-018 / T-011 are user- or SSH-driven; T-005 is `/grilling` with the user.

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
