# Hermes Agent Prompts

> Copy-pasteable, token-optimized prompts for the Lane A research tickets on the wayfinder chart. Each prompt is self-contained — paste into your agent. Standing preferences, GitHub URLs, and the D-013 close-comment shape are inline.
> Map: https://github.com/Noahlw/hermes/issues/1

## 1 · Standing preferences (locked on the map)

| # | Preference | Source |
|---|---|---|
| P-1 | LLM frontier = `MiniMax-M3` (OpenAI-compatible endpoint). Cheaper tier for narrow high-volume only | T-006 / D-006 context |
| P-2 | Self-hosted memory on the VM. Per-persona namespacing. Backup tarball + restore-test | D-002 / T-008 |
| P-3 | Cross-PC transport = Tailscale. **No public exposure of any service** | D-004 / D-005 |
| P-4 | API keys live in env-var only (`HERMES_MM_KEY` style). Rotate quarterly or on personnel change. **Never** in repo or in `config.yaml` | T-006 acceptance |
| P-5 | VM state under `/opt/hermes/{hermes,wiki,memories,backups,tailscale,run}` | D-006 |
| P-6 | Library + tool calls log per persona + per task type for cost tracking | T-023 |
| P-7 | Cross-PC surface = Hermes as librarian (`library_*` tools), not raw DB access | D-005 |

## 2 · Workflow — D-013 life-cycle

```
1. Read the issue body. Check blockers via `gh issue view <N> --json blockedBy`.
2. Claim: `gh issue edit <N> --repo Noahlw/hermes --add-assignee @me`.
3. Apply matt-pocock skills as needed (see per-prompt guidance).
4. Produce the deliverable. Post as a comment on the issue.
5. Close with D-013 spec:
   gh issue close <N> --repo Noahlw/hermes --comment-file spec.md
   where spec.md has sections: ## Rationale / ## Acceptance / ## Hand-off
6. After T-024 re-run, GRANDMAP.md absorbs the close.
```

A comment is the spec. Closing with `## Hand-off` means a future implementation ticket can spawn from it.

## 3 · Close-comment template (mandatory shape)

```markdown
## Rationale
- one bullet per decision
- (a)-(e): defend each pick in one sentence

## Acceptance
- artifact path or shape that will exist after implementation
- (repeat per artifact)

## Hand-off
Assignee: <agent ID or `none — closes here`>
Branch: `feat/T-NNN-<feature-slug>` (suggested; not enforced)
Scope: <what this spec covers; explicit "Not in scope" line below>
Not in scope: <so the impl agent doesn't drift>
Reference: <related issue numbers>
```

Sections missing → orchestrator prompts for completion; ticket stays open.

## 4 · Prompts — Lane A actionable now

The four prompts below map to four currently-actionable tickets (`label:lane:no-ssh`, `state:open`, no blockers, unassigned):

| Ticket | # | Best lane | Why |
|---|---|---|---|
| T-006 LLM tier routing | #7 | **Deep-reasoning** | Composing a YAML provider + delegation block + who-calls-which-model diagram from a comparative analysis is the canonical "spec it, defend it" task. |
| T-008 Memory backend | #9 | **Deep-reasoning** | Three-way comparison (Letta / Mem0+Qdrant / Hermes-native+Qdrant) across 6 dimensions plus a compose skeleton plus a backup procedure. |
| T-017 internal-wiki sample | #18 | **File-context** | Reading three files in `~/Desktop/code/internal-wiki/` and extracting vocabulary — single-shot summarization, no architecture calls. |
| T-025 Monthly recommender | #26 | **File-context** | Recurring refresh against an evolving tech landscape; lighter reasoning, more synthesis. |

T-005 (#6) is `wayfinder:grilling` and stays user-driven via `/grilling` skill — no agent prompt here.

---

### Prompt A · T-006 (#7) — LLM tier routing + provider YAML

```
You are the agent for one ticket on the Hermes wayfinder chart.

TICKET: https://github.com/Noahlw/hermes/issues/7
BODY: read the ticket before starting; the question, concrete shape, and acceptance
      sections define your deliverable exactly.

WHAT YOU ALREADY KNOW (do not re-derive):
- Standing preferences P-1, P-4 on this map.
- Hermes Agent uses YAML config at ~/.hermes/config.yaml with `providers:` and
  `delegation:` blocks; the upstream docs describe the schema.
- Output is a SPECIFICATION — no code lands in the repo on this ticket.
- An implementation ticket will spawn from your close-comment per D-013.

APPLY:
- /grilling or /spec when you need to sharpen an open question.
- /research when a fact about the upstream Hermes provider schema is unknown.

DELIVER — single comment on #7 with these four sections in order:

1. `providers:` block (YAML)
   - frontier: MiniMax-M3
   - cheaper tier: a sibling model in the same family (one sentence on the call)
   - env var name only (e.g. HERMES_MM_KEY); no secret in the snippet
   - base URL, auth header, model id per provider

2. `delegation:` block (YAML)
   - default provider = frontier
   - subagent override hook
   - retry policy + 429/5xx/key-missing fallback (each named, not "handled")

3. Routing diagram (6–8 lines, mermaid or text)
   - chat / persona response / librarian answer / memory recall embedding /
     wiki re-ranker / subagent fan-out
   - which task type lands on which model

4. `## Rationale` — defend (a) frontier pick (b) cheap-tier pick (c) failure-mode paths
   in one sentence each.

CLOSE per the workflow above. Your close-comment is the spec — it MUST include
## Acceptance (artifacts: yaml snippet + diagram + failure-mode table) and
## Hand-off (assignee, branch, scope line, "Not in scope" line).

DO NOT: run shell on the VM, write files outside #7's comment thread,
        touch any other ticket, paste API keys.
```

---

### Prompt B · T-008 (#9) — Memory backend research

```
You are the agent for one ticket on the Hermes wayfinder chart.

TICKET: https://github.com/Noahlw/hermes/issues/9
BODY: read the ticket before starting; the question, concrete shape, and acceptance
      sections define your deliverable exactly.

WHAT YOU ALREADY KNOW (do not re-derive):
- Standing preferences P-2 on this map.
- Three candidates: Letta self-host / Mem0 + Qdrant / Hermes-native ctx.storage + Qdrant.
- Default VM shape is Ubuntu; assume 8 GB RAM, 40 GB disk, single-host.
- Output is a SPECIFICATION — no deployments land in the repo on this ticket.

APPLY:
- /grilling to clarify the per-persona isolation requirement (P-2).
- /research on each candidate's pre_llm_call fit + active maintenance signal.

DELIVER — single comment on #9 with these four sections in order:

1. ONE-SENTENCE winner (e.g., "pick Mem0 + Qdrant because …"). Defend in ≤200 words.

2. Comparison table (6 rows × 3 columns):
   - dimension | Mem0+Qdrant | Letta self-host | Hermes-native+Qdrant
   - dimensions: write latency under 100 facts/min · recall quality (sample session)
   - ops surface (RAM/disk) · backup ergonomics · fit with pre_llm_call hook
   - per-persona namespacing strategy
   One column has the winner at each row — flag it.

3. `docker-compose.yml` skeleton for the chosen backend:
   services: <backend> <vector-DB>
   volumes: /opt/hermes/memories/{data,snapshots}
   ports: 127.0.0.1:<x> only — never 0.0.0.0

4. `## Rationale` — defend the winner against the two runners-up in two sentences.
   Include the per-persona namespacing approach (one paragraph).

CLOSE per the workflow above. Your close-comment is the spec — it MUST include
## Acceptance (compose skeleton + 6-row comparison + namespacing approach) and
## Hand-off (assignee, branch, scope line, "Not in scope" line).

DO NOT: deploy memory, run docker on this Mac, write files outside #9,
        train embeddings, recommend a model not in the same family as frontier.
```

---

### Prompt C · T-017 (#18) — Sample internal-wiki for prior art

```
You are the agent for one ticket on the Hermes wayfinder chart.

TICKET: https://github.com/Noahlw/hermes/issues/18
BODY: read the ticket before starting; the question, concrete shape, and acceptance
      sections define your deliverable exactly.

WHAT YOU ALREADY KNOW (do not re-derive):
- Source path: ~/Desktop/code/internal-wiki/ on the user's Mac.
- Per D-006: research input only. Do NOT copy files into the repo.
- This ticket has been REPURPOSED — it no longer feeds T-010 (closed D-010).
  It now feeds the grand map's Glossary section, period.
- Repurposed status: `phase:waiting-wiki-lift` label applied; remove the parking
  label only if the close-comment is rich enough to feed the Glossary directly.

APPLY:
- /research if a comparison term needs context (you won't, often).
- File reading tools — that's the entire job.

DELIVER — single comment on #18 with these three sections in order:

1. Up to 8 short bullets titled "Vocabulary + structural decisions worth carrying":
   - each bullet names ONE concept (term, design choice, taxonomy)
   - each bullet lists the source file path
   - format: `- <concept> — from <file>`

2. Up to 4 short bullets titled "Do not adopt (conflicts with standing preferences)":
   - each bullet names the conflict (which P-N it breaks)
   - format: `- <pattern> from <file> — conflicts with <P-N>`

3. `## Hand-off`:
   Assignee: <agent ID>
   Branch: `feat/T-017-internal-wiki-concepts`
   Scope: feed the Glossary section of GRANDMAP.md
   Not in scope: anything for the wiki's runtime behavior (D-010 parks that)

CLOSE per the workflow above. Your close-comment IS the glossary note;
post it once as a comment, then close with a single-line summary pointing at
the comment's timestamp.

DO NOT: copy files into the Hermes repo, edit anything under ~/Desktop/code/,
        spawn implementation tickets (this is a glossary input only).
```

---

### Prompt D · T-026 (no, T-025 — #26) — Monthly improvement recommender

```
You are the agent for one ticket on the Hermes wayfinder chart.

TICKET: https://github.com/Noahlw/hermes/issues/26
BODY: read the ticket before starting; the question, concrete shape, and acceptance
      sections define your deliverable exactly.

RECURRING TRIGGER:
- Cadence: monthly. Run again on day 30 (or later) after the last run.
- You MAY be invoked multiple times — each run is independent.

WHAT YOU ALREADY KNOW (do not re-derive):
- Standing preferences P-1 .. P-7 on this map.
- All other Hermеs tickets you've already absorbed (do pull recent decisions
  from the map body before starting).

APPLY:
- /research skill with one prompt: "monthly Herme upgrade/upgrade candidates".
- /grilling to clarify ambiguous recommendations before listing.

DELIVER — in this order:

A. Single comment on #26 with:
   1. A 6-line summary of what changed since last run (or "baseline" if first run).
   2. A flat list of 0..8 candidate updates/upgrades, each as:
      - Title (≤60 chars)
      - One-paragraph rationale
      - Which standing preference it touches (P-N)
      - Rough effort (S / M / L)
      - Risk (Low / Med / High)
      - Suggested lane (`lane:no-ssh` or `lane:ssh-gated`)

B. For each candidate the user wants to act on (user decides — you do NOT auto-spawn):
   the agent (or you, on user instruction) creates a fresh `phase:planning`
   child issue of map #1 with:
   - title (≤60 chars)
   - body in wayfinder template (## Question / ## Concrete shape / ## Acceptance)
   - labels: `wayfinder:research`, `lane:<A|B>` per agent judgment,
     `origin:auto-research`, `provenance:monthly-YYYY-MM`,
     `phase:planning`, `ready-for-agent`
   - body header: `Origin: T-025 monthly pass, YYYY-MM-DD`

CLOSE per the workflow above only after you have:
- posted the 6-line summary
- listed 0..8 candidates
- (any user-approved) tickets are already created

If candidates = 0 ("nothing's drifted"), that's a valid result; record it as
the rationale and close.

GUARD: do NOT spawn a `phase:recurring:monthly` ticket. Do NOT auto-close
       planning tickets from prior passes. Do NOT modify any closed ticket.
```

## 5 · Don'ts (universal)

- Don't paste API keys, SSH keys, or any secret into comments or files.
- Don't commit or push outside the user's repo / local clone.
- Don't auto-close tickets you didn't claim.
- Don't write to branches the user didn't authorize.
- Don't assume the user has T-001 closed — Lane B work stays parked.

## 6 · Commands you'll need

```bash
# Front-tier query (open + lane:no-ssh + unassigned + unblocked):
gh issue list --repo Noahlw/hermes \
  --state open --label 'lane:no-ssh' \
  --json number,title,labels,assignees,blockedBy \
  | jq '.[] | select(.assignees|length==0)
              | select(.blockedBy|not or (.blockedBy.nodes|length==0))
              | {n:.number, t:.title}'

# Claim:
gh issue edit <N> --repo Noahlw/hermes --add-assignee @me

# Close with D-013 spec:
# (write spec to /tmp/spec-<N>.md with the template in §3, then:)
gh issue close <N> --repo Noahlw/hermes --comment-file /tmp/spec-<N>.md

# Re-run grand-map compile (T-024 successor — orchestrator does this):
# use the same compile logic; re-emit Hermes/GRANDMAP.md and comment on #1.
```

## 7 · When you're done with a ticket

Tick the chart:

1. After closing, post one-liner on map #1:
   ```bash
   gh issue comment 1 --repo Noahlw/hermes --body \
     "- **D-NNN** — Resolved T-NNN: <one-line gist>; [#N](https://github.com/Noahlw/hermes/issues/N)."
   ```
2. Re-run T-024 (manual `/compile-grand-map`) to refresh GRANDMAP.md.
3. Done. Future work enters via T-025 monthly pass or by user-led ticket creation.

---

**End of prompts.** Standing preferences are at the top for a reason — they're the law any new agent must obey without re-asking.
