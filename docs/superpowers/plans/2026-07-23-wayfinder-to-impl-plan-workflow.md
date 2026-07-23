# Hermes Wayfinder → Implementation Plan Workflow

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define a repeatable workflow that converts each closed wayfinder planning ticket into a writing-plans-style implementation plan, executes it via a fresh subagent, and rolls the outcome back into the grand map.

**Architecture:** Orchestrator monitors `phase:planning` tickets. On close, it extracts the spec from the close comment, spawns a child `phase:implementation` issue, writes a writing-plans-style plan to `docs/superpowers/plans/YYYY-MM-DD-<ticket-id>-<feature>.md`, and dispatches a fresh agent on the impl ticket. When the impl ticket closes, the orchestrator updates the grand map. Plans are 1:1 with tickets; one plan per closed planning ticket.

**Tech Stack:** GitHub Issues (orchestration), `gh` CLI, `writing-plans` skill, Python 3.14 (orchestrator runtime), pytest (test framework).

## Global Constraints

- **LLM frontier**: `MiniMax-M3` (per D-006 via T-006 output).
- **Cross-PC transport**: Tailscale; no public exposure (per D-004, D-005).
- **Memory isolation**: per-persona namespaces (per D-002).
- **Lane discipline**: Lane A implements first; Lane B waits for T-001 close.
- **TDD**: every impl task writes a failing test before implementation.
- **Frequent commits**: one commit per step minimum; each ticket closes with a clean working tree.
- **No secret-in-commit**: API keys, tokens, SSH keys never land in the repo.

## File Structure & Changes

```
Hermes/
├── README.md                                            # existing — chart hub
├── conftest.py                                          # new — pytest path setup
├── orchestrator/
│   ├── __init__.py
│   ├── closure_listener.py                              # Task 1
│   ├── spec_extractor.py                                # Task 2
│   ├── impl_spawner.py                                  # Task 3
│   ├── plan_writer.py                                   # Task 4
│   ├── executor.py                                      # Task 5
│   └── grandmap_updater.py                              # Task 6
├── tests/orchestrator/
│   ├── test_closure_listener.py
│   ├── test_spec_extractor.py
│   ├── test_impl_spawner.py
│   ├── test_plan_writer.py
│   ├── test_executor.py
│   └── test_grandmap_updater.py
└── .github/
    └── workflows/
        └── orchestrator.yml                             # cron + event handler
```

## What Already Exists

- Wayfinder chart on GitHub: map #1, ~23 child tickets (5 closed, ~18 active).
- D-013 mandate: planning → spec → implementation.
- Local mirror repo `~/.../Hermes/` with `README.md`.
- `gh` CLI authenticated; Hermes Agent + Tailscale yet to be installed.

## Not In Scope

- Auto-implementing planning tickets before they close.
- Replacing the wayfinder chart with another format.
- Cross-impl parallelism orchestration (sequential first cut).

## ASCII Diagrams

### Lifecycle of a single ticket

```
┌─────────────────────────────────────────────────────────────────┐
│ wayfinder ticket #N, phase:planning                            │
└─────────────────────────────────────────────────────────────────┘
       │ assignee closes with markdown spec
       ▼
┌─────────────────────────────────────────────────────────────────┐
│ closure_listener + spec_extractor + impl_spawner              │
│ → spawns #M = phase:implementation, child of #N               │
│ → writes docs/superpowers/plans/<date>-<feature>.md           │
└─────────────────────────────────────────────────────────────────┘
       │ agent claims #M, runs the plan
       ▼
┌─────────────────────────────────────────────────────────────────┐
│ per-task: failing test → impl → test → commit → PR            │
└─────────────────────────────────────────────────────────────────┘
       │ #M closes
       ▼
┌─────────────────────────────────────────────────────────────────┐
│ grandmap_updater appends to Decisions so far on #1             │
│ T-024 re-runs once per quarter                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Failure Modes & Gaps

- **Close comment lacks a spec.** Fallback: orchestrator comments on the planning ticket requesting spec within 48h; if unresolved, escalates to user.
- **Impl ticket assignee abandons.** Re-claim via orchestrator after 7 days idle.
- **Plan saved but impl fails to execute.** Keep impl ticket open; orchestrator posts error transcript.
- **Spec contradicts chart's standing preferences.** Orchestrator flags before spawn.

## Parallelization / Worktree Strategy

- Different wayfinder tickets can resolve in parallel by agents in different sessions.
- Different impl tickets touching different files execute in parallel (each in its own git worktree under `Hermes/.worktrees/<ticket-id>`).
- Same-file conflicts serialize via orchestrator lease.

---

## Task 1: Build the closure-listener script

**Files:**
- Create: `orchestrator/closure_listener.py`
- Create: `tests/orchestrator/test_closure_listener.py`
- Create: `.github/workflows/orchestrator.yml`

**Interfaces:**
- Consumes: `gh issue list --repo <repo> --state closed --label phase:planning --json number,title,body,closedAt,comments`
- Produces: `list[ClosedPlanningTicket]` for tickets not yet logged to `orchestrator/state/processed.json`
- `ClosedPlanningTicket` dataclass: `number: int`, `title: str`, `body: str`, `spec_text: str`, `closed_at: datetime`

- [ ] **Step 1: Write a failing test** — `test_fetch_new_planning_closes_returns_recently_closed`
- [ ] **Step 2: Run test to verify it fails** — `pytest tests/orchestrator/test_closure_listener.py::test_fetch_new_planning_closes_returns_recently_closed -v`
- [ ] **Step 3: Implement** — `ClosureListener` class, `ClosedPlanningTicket` dataclass, JSON state persistence
- [ ] **Step 4: Run test to verify it passes** — same command as Step 2
- [ ] **Step 5: Wire the workflow trigger** — `.github/workflows/orchestrator.yml` cron + workflow_dispatch
- [ ] **Step 6: Commit** — `feat(orchestrator): closure-listener for wayfinder planning closes`

---

## Task 2: Spec-extraction utility

**Files:**
- Create: `orchestrator/spec_extractor.py`
- Create: `tests/orchestrator/test_spec_extractor.py`

**Interfaces:**
- Consumes: `ClosedPlanningTicket.spec_text`
- Produces: `Spec` dataclass with `headline: str`, `rationale_bullets: list[str]`, `acceptance_artifacts: list[str]`, `hand_off: str`, `incomplete: bool`

- [ ] **Step 1: Write a failing test** — `test_extract_spec_parses_three_sections`
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement** — `extract_spec(markdown: str) -> Spec` over `## Rationale`, `## Acceptance`, `## Hand-off` sections
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit** — `feat(orchestrator): spec extractor`

---

## Task 3: Implementation-ticket spawner

**Files:**
- Create: `orchestrator/impl_spawner.py`
- Create: `tests/orchestrator/test_impl_spawner.py`

**Interfaces:**
- Consumes: `ClosedPlanningTicket`, `Spec`
- Produces: GitHub issue via `gh issue create`; returns impl ticket number

- [ ] **Step 1: Write a failing test** — `test_spawn_impl_ticket_parses_url`
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement** — `spawn_impl_ticket(planning, spec, repo, dry_run=False)`
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit** — `feat(orchestrator): spawn implementation ticket per closed planning ticket`

---

## Task 4: Plan-writer

**Files:**
- Create: `orchestrator/plan_writer.py`
- Create: `docs/superpowers/plans/README.md`
- Create: `tests/orchestrator/test_plan_writer.py`

**Interfaces:**
- Consumes: `Spec`, `ClosedPlanningTicket`
- Produces: a file at `docs/superpowers/plans/YYYY-MM-DD-T-NNN-<feature>.md`

- [ ] **Step 1: Write a failing test** — `test_write_plan_creates_file_with_today_date`
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement** — `write_plan(spec, ticket, output_dir, today)` from `writing-plans` template
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Create `docs/superpowers/plans/README.md`** — index
- [ ] **Step 6: Commit** — `feat(orchestrator): plan writer integrating writing-plans skill template`

---

## Task 5: Hand-off to agent executor

**Files:**
- Create: `orchestrator/executor.py`
- Create: `tests/orchestrator/test_executor.py`

**Interfaces:**
- Consumes: impl ticket number, plan path
- Produces: a dispatched agent session id; ability to comment status

- [ ] **Step 1: Write a failing test** — `test_dispatch_agent_dry_run`
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement** — `dispatch_agent(ticket_number, plan_path, repo, dry_run=False)`, `comment_status(...)`
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit** — `feat(orchestrator): agent dispatcher for implementation tickets`

---

## Task 6: Grand-map rebuilder

**Files:**
- Create: `orchestrator/grandmap_updater.py`
- Create: `tests/orchestrator/test_grandmap_updater.py`

**Interfaces:**
- Consumes: closed impl ticket number, gist string
- Produces: comment on map #1; optional monthly trigger of T-024

- [ ] **Step 1: Write a failing test** — `test_append_decision_idempotent`
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement** — `append_decision_to_map(...)`, `trigger_full_rebuild(...)`
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Wire into orchestrator.yml** — monthly cron for full rebuild
- [ ] **Step 6: Commit** — `feat(orchestrator): grand-map rebuilder wired to impl closes`

---

## Self-Review Checklist

- **Spec coverage**: D-013 mandates planning→spec→impl; this plan creates the bridge.
- **Instruction clarity**: each task names files, function signatures, types, expected behavior.
- **Type consistency**: `ClosedPlanningTicket` and `Spec` defined once in Tasks 1/2, used in 3-6.
- **Boring default**: pure Python + stdlib + pytest.
- **Reversibility**: each task is one atomic commit; rollback is `git revert <hash>`.
- **Essentials over accidental**: no CI bells; sequential first cut.
