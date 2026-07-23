"""Orchestrator: grand-map rebuilder.

After impl tickets close, appends a one-line gist to the wayfinder map's
"Decisions so far" section via `gh issue comment`. Triggered by:
- Every successful impl-ticket close
- A monthly cron for the full grand-map rebuild (T-024)

Idempotency: each impl ticket is logged exactly once via `state_file`.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

MAP_ISSUE = 1


def _read_state(state_file: Path) -> dict[str, str]:
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state(state_file: Path, data: dict[str, str]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(data, indent=2, sort_keys=True))


def append_decision_to_map(
    impl_ticket_number: int,
    gist: str,
    state_file: Path,
    repo: str = "Noahlw/hermes",
    gh_bin: str = "gh",
    dry_run: bool = False,
) -> bool:
    """Append `- **D-NEW** — Resolved #{impl_ticket_number}: <gist>` to map #1.

    Returns True if appended; False if already logged.
    """
    state = _read_state(state_file)
    key = str(impl_ticket_number)
    if key in state:
        return False

    body = f"- **D-new** — Resolved #{impl_ticket_number}: {gist}\n"
    if dry_run:
        _write_state(state_file, {**state, key: datetime.now().isoformat()})
        return True

    cmd = [
        gh_bin, "issue", "comment", str(MAP_ISSUE),
        "--repo", repo,
        "--body", body,
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    _write_state(state_file, {**state, key: datetime.now().isoformat()})
    return True


def trigger_full_rebuild(repo: str = "Noahlw/hermes", gh_bin: str = "gh", dry_run: bool = False) -> int:
    """Trigger T-024 (Compile grand map) — comment on the issue to wake its
    assignee. Returns 0 in dry-run, else the new comment number (or 0).
    """
    body = "@orchestrator: monthly rebuild triggered at " + datetime.now().isoformat() + \
           ". Please re-author GRANDMAP.md from current state."
    if dry_run:
        return 0
    cmd = [
        gh_bin, "issue", "comment", "25",  # T-024 lives at issue #25 after Phase D
        "--repo", repo,
        "--body", body,
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return 0
