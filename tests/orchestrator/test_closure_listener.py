"""Tests for orchestrator.closure_listener."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from orchestrator.closure_listener import ClosedPlanningTicket, ClosureListener


def test_fetch_new_planning_closes_returns_recently_closed(tmp_path: Path, mocker):
    """Verify fetch_new_planning_closes returns tickets not in state_file."""
    listener = ClosureListener(
        repo="Noahlw/hermes",
        state_file=tmp_path / "processed.json",
    )
    # Mock the gh call
    fake_gh_output = json.dumps([
        {
            "number": 7,
            "title": "T-006 LLM tier routing",
            "body": "**Question**",
            "closedAt": "2026-07-23T10:00:00Z",
            "comments": {"nodes": [{"body": "## Rationale\n- bullet one"}]},
        },
        {
            "number": 6,
            "title": "T-005 already-processed",
            "body": "...",
            "closedAt": "2026-07-22T10:00:00Z",
            "comments": {"nodes": []},
        },
    ])
    mocker.patch("subprocess.run", return_value=_FakeResult(fake_gh_output))

    # Only ticket 7 is new (6 is in state_file)
    (tmp_path / "processed.json").write_text(json.dumps({"6": "2026-07-22T10:00:00Z"}))

    tickets = listener.fetch_new_planning_closes()
    assert len(tickets) == 1
    assert tickets[0].number == 7
    assert "Rationale" in tickets[0].spec_text


def test_fetch_new_returns_empty_when_all_processed(tmp_path: Path, mocker):
    listener = ClosureListener(repo="Noahlw/hermes", state_file=tmp_path / "processed.json")
    fake_gh = json.dumps([
        {"number": 6, "title": "x", "body": "y", "closedAt": "2026-07-22T10:00:00Z", "comments": {"nodes": []}},
    ])
    mocker.patch("subprocess.run", return_value=_FakeResult(fake_gh))
    (tmp_path / "processed.json").write_text(json.dumps({"6": "2026-07-22T10:00:00Z"}))

    assert listener.fetch_new_planning_closes() == []


def test_mark_processed_is_idempotent(tmp_path: Path):
    listener = ClosureListener(repo="Noahlw/hermes", state_file=tmp_path / "processed.json")
    (tmp_path / "processed.json").write_text("{}")
    t1 = ClosedPlanningTicket(number=8, title="x", body="", spec_text="", closed_at=datetime.now())
    listener.mark_processed([t1])
    listener.mark_processed([t1])
    data = json.loads((tmp_path / "processed.json").read_text())
    assert list(data.keys()) == ["8"]


def test_state_file_missing_is_fine(tmp_path: Path, mocker):
    listener = ClosureListener(repo="Noahlw/hermes", state_file=tmp_path / "missing.json")
    mocker.patch("subprocess.run", return_value=_FakeResult("[]"))
    assert listener.fetch_new_planning_closes() == []


class _FakeResult:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode

    def check_returncode(self):
        if self.returncode != 0:
            raise subprocess.CalledProcessError(self.returncode, [])
