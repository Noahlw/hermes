# Hermes Agent Prompts — v2

> Copy-pasteable, token-optimized prompts for the v2 wayfinder chart.
> Each prompt is self-contained — paste into your agent.
> Standing preferences, GitHub URLs, and the D-013 close-comment shape are inline.
> Map: https://github.com/Noahlw/hermes/issues/27

## 1 · Standing preferences (locked on the map)

| # | Preference | Source |
|---|---|---|
| P-1 | LLM provider = **MiniMax-only** (single provider, no fallback chain). Model: `MiniMax-M3` (OpenAI-compatible endpoint). API key in `HERMES_MM_KEY` env var only | D-017 |
| P-2 | Self-hosted memory on the VM. Triple-stack: Qdrant + mem0 + agentmemory + Honcho | D-002 |
| P-3 | Cross-PC transport = Tailscale. **No public exposure of any service** | D-004 / D-005 |
| P-4 | API keys live in env-var only (`~/.hermes/.env`, mode 600). Rotate quarterly or on personnel change. **Never** in repo or in `config.yaml` | D-017 / P-4 v1 |
| P-5 | VM state under `/home/ubuntu/.hermes/` — all configs, data, profiles, scripts | D-015 |
| P-6 | Wiki + librarian surface deferred until core functionality lands | D-010 |
| P-7 | Cross-PC surface = Hermes as librarian (`library_*` tools), not raw DB access | D-005 |

## 2 · Workflow — D-013 life-cycle

```
1. Read the issue body. Check blockers via `gh issue view <N> --json blockedBy`.
2. Claim: `gh issue edit <N> --repo Noahlw/hermes --add-assignee @me`.
3. Produce the deliverable. Post as a comment on the issue.
4. Close with D-013 spec:
   gh issue close <N> --repo Noahlw/hermes --comment-file spec.md
   where spec.md has sections: ## Rationale / ## Acceptance / ## Hand-off
5. After close, GRANDMAP.md absorbs the result.
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

## 4 · Prompts — actionable tickets

| Ticket | # | Lane | Why |
|---|---|---|---|
| T-NEW-02 | #28 | ssh-gated | Ship 5-step hermes-setup-plan.md to done |
| T-NEW-03 | #29 | ssh-gated | Audit memory stack (Qdrant + mem0 + agentmemory + Honcho) |
| T-NEW-04 | #30 | ssh-gated | Design persona menu from SOUL.md + existing profiles |
| T-NEW-05 | #31 | ssh-gated | Token-cost ledger from kanban.db + Honcho derived |
| T-NEW-06 | #32 | ssh-gated | hermes-status heartbeat + Tailscale on remaining PCs |
| T-NEW-07 | #33 | ssh-gated | **Parked** — Wiki + librarian MCP chain (deferred per D-010) |
| T-NEW-08 | #34 | no-ssh | Monthly improvement recommender cron |
| T-NEW-09 | #35 | no-ssh | GRANDMAP.md recompile (T-024 successor, invoked on chart events) |
| T-NEW-10 | #36 | ssh-gated | Rotate leaked RSA SSH key — security debt |

---

### Prompt A · T-NEW-02 (#28) — Ship the five-step setup plan

```
You are the agent for one ticket on the Hermes wayfinder chart.

TICKET: https://github.com/Noahlw/hermes/issues/28
BODY: read the ticket before starting; the question, concrete shape, and acceptance
      sections define your deliverable exactly.

WHAT YOU ALREADY KNOW (do not re-derive):
- Standing preferences P-1..P-7 on this map.
- Existing VM state: Hermes Agent v0.15.1 installed at /home/ubuntu/.hermes/,
  triple-stack memory running, Docker compose stack up.
- A 5-step plan exists at /home/ubuntu/.hermes/hermes-setup-plan.md on the VM.
- Step 1 (provider chain) is SUPERSEDED by D-017 (MiniMax-only) — skip or adapt.
- Output is an IMPLEMENTATION — you SSH into the VM and run steps.

DELIVER:
1. SSH to the VM (key from ~/.hermes/.env or ~/.ssh/).
2. Read the current plan at /home/ubuntu/.hermes/hermes-setup-plan.md.
3. For each step still outstanding after D-017:
   - Apply config changes, run scripts, verify each step.
4. Post a comment on #28 with:
   - Which steps were already done (skip)
   - Which steps were modified for MiniMax-only
   - Which steps you executed and their output
5. Update the plan file (or write a done marker) on the VM.

CLOSE per §3 above. Your close-comment MUST include ## Acceptance
(e.g. "all 5 steps verified, plan file annotated with done-dates") and
## Hand-off (assignee, branch, scope line, "Not in scope" line).

DO NOT: paste API keys, modify any non-plan config outside the 5 steps,
        touch other tickets, run destructive commands.
```

---

### Prompt B · T-NEW-03 (#29) — Memory architecture audit

```
You are the agent for one ticket on the Hermes wayfinder chart.

TICKET: https://github.com/Noahlw/hermes/issues/29
BODY: read the ticket before starting; the question, concrete shape, and acceptance
      sections define your deliverable exactly.

WHAT YOU ALREADY KNOW (do not re-derive):
- Standing preferences P-2 on this map.
- Triple-stack: Qdrant (qdrant_mem0), mem0 (~/.hermes/mem0.json),
  agentmemory (agentmemory.service port 8642), Honcho (postgres+redis+api+deriver).
- These are already running on the VM (probe confirmed).
- This is a SPECIFICATION ticket — no changes land on the VM.

DELIVER — single comment on #29 with:

1. Architecture diagram (mermaid or text):
   - Which service owns what namespace / collection
   - Write path: what hooks push facts to each store
   - Read path: what the persona query looks like (recall call)

2. Consolidation recommendation:
   - One sentence: keep-all vs merge vs retire one
   - Defend in ≤200 words

3. Per-persona namespacing approach:
   - How default vs coder profiles isolate their memory

4. Backup procedure (one paragraph):
   - Cron script shape, tarball targets, restore test cadence

5. ## Rationale / ## Acceptance / ## Hand-off per §3

DO NOT: run shell on the VM, write configs, restart services,
        modify any container, touch backlogged tickets.
```

---

### Prompt C · T-NEW-04 (#30) — Persona menu

```
You are the agent for one ticket on the Hermes wayfinder chart.

TICKET: https://github.com/Noahlw/hermes/issues/30
BODY: read the ticket before starting; the question, concrete shape, and acceptance
      sections define your deliverable exactly.

WHAT YOU ALREADY KNOW (do not re-derive):
- Standing preferences P-2 (memory), P-1 (MiniMax-only).
- Two existing profiles on the VM: default and coder.
- SOUL.md exists as a persona descriptor file — path TBD on VM.
- This is a SPECIFICATION ticket — no changes land on the VM.

DELIVER — single comment on #30 with:

1. Persona menu spec (YAML or JSON):
   - Profile names, descriptions, which memory namespace each uses
   - Default persona assignment on first visit

2. Pre_llm_call hook design:
   - Where SOUL.md + profile config are injected into the system prompt
   - One code sketch (≤30 lines, pseudo or Python)

3. Switching UX:
   - How the user selects a persona (hermes command? env var? config?)
   - Example: `hermes --persona coder`

4. ## Rationale / ## Acceptance / ## Hand-off per §3

DO NOT: run shell on the VM, modify any config, touch backlogged tickets.
```

---

### Prompt D · T-NEW-08 (#34) — Monthly improvement recommender

```
You are the agent for one ticket on the Hermes wayfinder chart.

TICKET: https://github.com/Noahlw/hermes/issues/34
BODY: read the ticket before starting; the question, concrete shape, and acceptance
      sections define your deliverable exactly.

RECURRING TRIGGER:
- Cadence: monthly. First run TBD.
- You MAY be invoked multiple times — each run is independent.

WHAT YOU ALREADY KNOW (do not re-derive):
- Standing preferences P-1..P-7 on this map.
- Self-hosted Hermes Agent v0.15.1 on aarch64 Ubuntu VM.
- All other open Hermes tickets (pull recent decisions from the map before starting).

APPLY:
- /research skill with prompt: "monthly Hermes Agent upgrade/upgrade candidates".
- /grilling to clarify ambiguous recommendations before listing.

DELIVER — in this order:

A. Single comment on #34 with:
   1. A 6-line summary of what changed since last run (or "baseline" if first run).
   2. A flat list of 0..8 candidate updates/upgrades, each as:
      - Title (≤60 chars)
      - One-paragraph rationale
      - Which standing preference it touches (P-N)
      - Rough effort (S / M / L)
      - Risk (Low / Med / High)
      - Suggested lane (`lane:no-ssh` or `lane:ssh-gated`)

B. For each candidate the user wants to act on:
   Create a fresh `phase:planning` child issue of map #27 with:
   - title (≤60 chars)
   - body in wayfinder template (## Question / ## Concrete shape / ## Acceptance)
   - labels: `wayfinder:research`, `lane:<A|B>`, `origin:auto-research`,
     `provenance:monthly-YYYY-MM`, `phase:planning`, `ready-for-agent`

CLOSE per §3 only after you have:
- posted the 6-line summary
- listed 0..8 candidates
- (any user-approved) tickets are already created

If candidates = 0, that's valid — record it as the rationale and close.
```

---

### Prompt E · T-NEW-10 (#36) — Rotate leaked RSA SSH key

```
You are the agent for one ticket on the Hermes wayfinder chart.

TICKET: https://github.com/Noahlw/hermes/issues/36
BODY: read the ticket before starting; the question, concrete shape, and acceptance
      sections define your deliverable exactly.

WHAT YOU ALREADY KNOW (do not re-derive):
- D-016: leaked RSA key accepted as security debt, now being rotated.
- Current access: RSA private key was pasted in chat — still live on VM.
- Tailscale SSH is a recommended replacement: VM at 100.79.87.93,
  this Mac at 100.104.102.94.
- This is an IMPLEMENTATION ticket — you SSH in, rotate keys, test.

DELIVER:
1. Generate a new SSH key pair on the Mac (ed25519 preferred).
2. SSH to the VM using the OLD key (last access before rotation).
3. Replace the authorized_key entry with the new public key.
4. Optionally enable Tailscale SSH on the VM side.
5. Test that the new key works and the old key is rejected.
6. Post a comment on #36 with:
   - New key fingerprint (public part only — never paste the private key)
   - Whether Tailscale SSH was also enabled
7. Update ~/.ssh/config on the Mac if needed.

CLOSE per §3 above.

DO NOT: paste the new private key anywhere, write it to files in the repo,
        share fingerprints in public channels.
```

## 5 · Don'ts (universal)

- Don't paste API keys, SSH keys, or any secret into comments or files.
- Don't commit or push outside the user's repo / local clone.
- Don't auto-close tickets you didn't claim.
- Don't write to branches the user didn't authorize.
- Don't assume v1 tickets are still open — chart was restarted as v2 (#27).

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
```

## 7 · When a ticket closes

1. After closing via gh, update GRANDMAP.md locally:
   - Move the row from "Open tickets" to "Closed tickets"
   - Update the ticket count header
2. Commit and push GRANDMAP.md.
3. Done. Future work enters via T-NEW-08 monthly pass or user-led ticket creation.

---

**End of prompts v2.** Standing preferences are at the top for a reason — they're the law any new agent must obey without re-asking.
