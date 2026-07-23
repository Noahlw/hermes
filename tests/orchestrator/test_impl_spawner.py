"""Tests for orchestrator.impl_spawner."""

from datetime import datetime

import pytest

from orchestrator.impl_spawner import build_issue_body, build_issue_title, spawn_impl_ticket
from orchestrator.closure_listener import ClosedPlanningTicket
from orchestrator.spec_extractor import Spec


def _ticket(number: int = 7, title: str = "[T-006] LLM tier routing + provider YAML") -> ClosedPlanningTicket:
    return ClosedPlanningTicket(
        number=number,
        title=title,
        body="",
        spec_text="",
        closed_at=datetime(2026, 7, 23),
    )


def _spec() -> Spec:
    return Spec(
        headline="Provider YAML",
        rationale_bullets=["r1"],
        acceptance_artifacts=["a1"],
        hand_off="to dev-1.",
    )


def test_build_issue_title_strips_existing_prefix():
    t = _ticket(title="[T-006] LLM tier routing + provider YAML")
    title = build_issue_title(t)
    assert title.startswith("[T-006.IMPLEMENT]")
    assert "LLM tier routing" in title


def test_build_issue_title_handles_no_prefix():
    t = _ticket(title="LLM tier routing")
    title = build_issue_title(t)
    assert title.startswith("[T-?DEFINE-FEATURE.IMPLEMENT]")


def test_build_issue_body_includes_spec_and_source():
    t = _ticket()
    body = build_issue_body(t, _spec())
    assert "Closed planning ticket: #7" in body
    assert "## Spec" in body
    assert "Provider YAML" in body


def test_spawn_impl_ticket_dry_run(mocker):
    runner = mocker.patch("orchestrator.impl_spawner.subprocess.run")
    n = spawn_impl_ticket(_ticket(), _spec(), repo="Noahlw/hermes", dry_run=True)
    assert n == 0
    runner.assert_not_called()


def test_spawn_impl_ticket_parses_url(mocker):
    fake = mocker.Mock()
    fake.stdout = "https://github.com/Noahlw/hermes/issues/42\n"
    fake.returncode = 0
    mocker.patch("orchestrator.impl_spawner.subprocess.run", return_value=fake)
    n = spawn_impl_ticket(_ticket(), _spec(), repo="Noahlw/hermes", dry_run=False)
    assert n == 42
