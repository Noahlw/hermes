"""Tests for orchestrator.plan_writer."""

from datetime import datetime
from pathlib import Path

from orchestrator.plan_writer import _slugify, plan_filename, write_plan
from orchestrator.closure_listener import ClosedPlanningTicket
from orchestrator.spec_extractor import Spec


def _ticket() -> ClosedPlanningTicket:
    return ClosedPlanningTicket(
        number=7,
        title="[T-006] LLM tier routing + provider YAML",
        body="",
        spec_text="",
        closed_at=datetime(2026, 7, 23),
    )


def _spec() -> Spec:
    return Spec(
        headline="T-006 spec",
        rationale_bullets=["r1", "r2"],
        acceptance_artifacts=["artifact A", "artifact B"],
        hand_off="to dev-1",
    )


def test_slugify_basic():
    assert _slugify("Hello World!") == "hello-world"
    assert _slugify("[T-006] LLM Tier") == "t-006-llm-tier"


def test_plan_filename_format():
    today = "2026-07-23"
    path = plan_filename(_ticket(), today)
    assert path.startswith(today + "-T-006-")
    assert path.endswith(".md")


def test_write_plan_creates_file_with_today_date(tmp_path: Path):
    today = "2026-07-23"
    spec = Spec(
        headline="T-006 spec",
        rationale_bullets=[],
        acceptance_artifacts=[],
        hand_off="",
    )
    path = write_plan(spec, _ticket(), tmp_path, today=today)
    assert path.exists()
    assert path.name.startswith(today)
    assert "T-006" in path.name
    assert "## Rationale" in path.read_text()
    assert "## Hand-off" in path.read_text()


def test_write_plan_renders_one_task_per_acceptance(tmp_path: Path):
    spec = Spec(
        headline="spec",
        rationale_bullets=["r"],
        acceptance_artifacts=["first", "second"],
        hand_off="",
    )
    path = write_plan(spec, _ticket(), tmp_path, today="2026-07-23")
    text = path.read_text()
    assert "### Task 1" in text
    assert "### Task 2" in text
    assert "first" in text and "second" in text
