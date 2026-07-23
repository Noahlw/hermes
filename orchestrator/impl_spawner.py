"""Orchestrator: implementation-ticket spawner.

Builds a child issue for a closed planning ticket. The child has:
- `--parent` linking to the planning ticket
- `phase:implementation` label
- `--title` like `[T-NNN.IMPLEMENT] <feature>`
- body = spec verbatim (markdown), with a header linking back to the planning ticket.

Returns the new issue number; non-zero on dry-run when `dry_run=True`.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from .closure_listener import ClosedPlanningTicket
from .spec_extractor import Spec


_TICKET_NUM_RE = re.compile(r"T-(\d+)", re.IGNORECASE)


def ticket_id_from_title(title: str) -> str:
    """Extract `T-NNN` from a wayfinder title. Fallback: `T-?`."""
    m = _TICKET_NUM_RE.search(title)
    if m:
        return f"T-{m.group(1).zfill(3)}"
    return "T-?DEFINE-FEATURE"


def build_issue_body(planning: ClosedPlanningTicket, spec: Spec) -> str:
    body_lines = [
        "Implementation of the spec from #{planning_number} ({planning_title}).".format(
            planning_number=planning.number,
            planning_title=planning.title,
        ),
        "",
        "## Source",
        f"Closed planning ticket: #{planning.number}",
        "",
        "## Spec",
        "",
        spec.to_markdown(),
        "",
        "## How to work this ticket",
        "- Do NOT modify the closed planning ticket.",
        "- Read the spec above; write a writing-plans-style plan in `docs/superpowers/plans/`.",
        "- Implement against the plan, TDD-style, frequent commits.",
        "- Close when all acceptance artifacts are produced.",
    ]
    return "\n".join(body_lines)


def build_issue_title(planning: ClosedPlanningTicket) -> str:
    ticket_id = ticket_id_from_title(planning.title)
    feature = planning.title.strip() or "implementation"
    if feature.lower().startswith(ticket_id.lower()):
        feature = feature[len(ticket_id):].strip(" -–:")
    if not feature:
        feature = "implementation"
    return f"[{ticket_id}.IMPLEMENT] {feature}"


def spawn_impl_ticket(
    planning: ClosedPlanningTicket,
    spec: Spec,
    repo: str,
    gh_bin: str = "gh",
    dry_run: bool = False,
) -> int:
    """Create the impl issue. Returns the new issue number, or 0 in dry-run."""
    title = build_issue_title(planning)
    body = build_issue_body(planning, spec)
    labels = "phase:implementation,wayfinder:task"

    if dry_run:
        return 0

    cmd = [
        gh_bin, "issue", "create",
        "--repo", repo,
        "--title", title,
        "--body", body,
        "--label", labels,
        "--parent", str(planning.number),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    # `gh issue create` prints the issue URL on the last stdout line.
    url = (result.stdout or "").strip().splitlines()[-1]
    m = re.search(r"/issues/(\d+)", url)
    return int(m.group(1)) if m else 0
