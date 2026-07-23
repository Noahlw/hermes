"""Orchestrator: plan-writer.

Writes a writing-plans-style markdown plan for a closed planning ticket.
The plan body is templated from `Spec.headline`, `Spec.rationale_bullets`,
`Spec.acceptance_artifacts`, and `Spec.hand_off`. The plan file lives at
`docs/superpowers/plans/YYYY-MM-DD-T-NNN-<feature>.md`.

Plans contain no runnable code. They are the spec for the implementer.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .closure_listener import ClosedPlanningTicket
from .impl_spawner import ticket_id_from_title
from .spec_extractor import Spec


def _slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "impl"


def _features_from_acceptance(spec: Spec) -> list[str]:
    """Treat each acceptance bullet as a feature sketch."""
    return spec.acceptance_artifacts or ["(no acceptance artifacts — flesh out during impl)"]


def plan_filename(ticket: ClosedPlanningTicket, today: str) -> str:
    ticket_id = ticket_id_from_title(ticket.title)
    feature = _slugify(re.sub(r"T-\d+\s*", "", ticket.title, flags=re.IGNORECASE).strip(" -–:[]"))
    return f"{today}-{ticket_id}-{feature}.md"


def write_plan(
    spec: Spec,
    ticket: ClosedPlanningTicket,
    output_dir: Path,
    today: str | None = None,
) -> Path:
    """Write a writing-plans-style plan to `output_dir / plan_filename(...)`.

    Returns the absolute path to the written plan.
    """
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / plan_filename(ticket, today)

    ticket_id = ticket_id_from_title(ticket.title)
    feature = ticket.title.strip() or ticket_id
    tasks = _features_from_acceptance(spec)

    body = _render_plan(
        title=f"{ticket_id} {feature} Implementation Plan",
        goal=spec.headline or f"Implement {feature} per the planning ticket's spec.",
        rationale=spec.rationale_bullets,
        tasks=tasks,
        hand_off=spec.hand_off,
        ticket_id=ticket_id,
        feature=feature,
    )

    path.write_text(body)
    return path


def _render_plan(
    title: str,
    goal: str,
    rationale: list[str],
    tasks: list[str],
    hand_off: str,
    ticket_id: str = "",
    feature: str = "",
) -> str:
    rationale_md = "\n".join(f"- {r}" for r in rationale) or "- (fill in)"
    task_blocks = []
    for i, t in enumerate(tasks, start=1):
        task_blocks.append(_render_task(i, t, ticket_id=ticket_id))
    tasks_md = "\n\n---\n\n".join(task_blocks) or "_No tasks derived yet — write at least one._"

    worktree = f"Hermes/.worktrees/{ticket_id.lower()}" if ticket_id else "Hermes/.worktrees/<ticket>"

    return f"""# {title}

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** {goal}

**Architecture:** This implementation realizes the spec derived from a closed planning ticket. Strict TDD: failing test → impl → test → commit. One atomic commit per step.

**Tech Stack:** Python 3.12 (orchestrator runtime). Implementation language determined by the feature; consult the parent planning ticket.

## Global Constraints

- LLM frontier is `MiniMax-M3` for chat/reasoning; cheaper model only for narrow high-volume tasks (per standing preference).
- Self-hosted memory has per-persona namespaces (do not leak librarian memory to other personas).
- No secrets in commit; API keys via env vars only.
- One logical change per step; one commit per step.

## File Structure & Changes

_Derive from the task list below before implementing._ (Implementer: enumerate the files each task touches; add new files only when needed.)

## What Already Exists

- The wayfinder chart on github.com/Noahlw/hermes (this issue references it).
- `orchestrator/` modules: `closure_listener.py`, `spec_extractor.py`, `impl_spawner.py`, `plan_writer.py`.
- `docs/superpowers/plans/` directory and `README.md` index.

## Not In Scope

- Modification of the closed planning ticket.
- Updates to the wayfinder map (`#1`); orchestration rolls back via `grandmap_updater.py`.
- Cross-feature refactors; touch only what the spec calls for.

## ASCII Diagrams

_Add as needed; the implementer fills this in if the task has non-obvious state flow._

## Failure Modes & Gaps

- Acceptance artifacts ambiguous: re-open planning ticket for clarification.
- Plan turns out to require a third task: append Task N+1, don't restructure existing tasks.
- Cross-feature dependency discovered: stop and request a new planning ticket.

## Parallelization / Worktree Strategy

Implementer executes in `{worktree}` (a worktree created off `main`). Commit, push branch, open PR; PR review before merge to main.

---

## Rationale

{rationale_md}

---

{tasks_md}

---

## Hand-off

{hand_off or "_Fill in at close: assignee, branch, reviewer._"}
"""


def _render_task(index: int, intent: str, ticket_id: str = "") -> str:
    return f"""### Task {index}: {intent}

**Files:**
- Create: _list files here at impl-time_
- Modify: _list files here at impl-time_
- Test: _list tests here at impl-time_

**Interfaces:**
- Consumes: _inputs and prior task contracts_
- Produces: _outputs and downstream task contracts (exact signatures)_

- [ ] **Step 1: Write a failing test** — describe the test intent and expected failure message.
- [ ] **Step 2: Run test to verify it fails** — exact command + expected failure.
- [ ] **Step 3: Implement minimal code to pass** — function/type names, parameter and return types, behavior.
- [ ] **Step 4: Run test to verify it passes** — same command as Step 2, expected PASS.
- [ ] **Step 5: Commit** — message, files staged.
"""
