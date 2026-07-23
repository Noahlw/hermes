"""Tests for orchestrator.spec_extractor."""

from orchestrator.spec_extractor import Spec, extract_spec


def test_extract_spec_parses_three_sections():
    raw = """## Rationale
- bullet one
- bullet two

## Acceptance
- artifact one
- artifact two

## Hand-off
Assignee: dev-1. Branch: feat/T-006-llm-tier.
"""
    spec = extract_spec(raw)
    assert spec.rationale_bullets == ["bullet one", "bullet two"]
    assert spec.acceptance_artifacts == ["artifact one", "artifact two"]
    assert "dev-1" in spec.hand_off


def test_extract_spec_handles_missing_sections():
    raw = "## Rationale\n- only rationale"
    spec = extract_spec(raw)
    assert spec.rationale_bullets == ["only rationale"]
    assert spec.acceptance_artifacts == []
    assert spec.hand_off == ""
    assert spec.incomplete is True


def test_extract_spec_numbered_lists():
    raw = """## Acceptance
1. first
2. second
"""
    spec = extract_spec(raw)
    assert spec.acceptance_artifacts == ["first", "second"]


def test_to_markdown_round_trip():
    raw = """## Rationale
- r1

## Acceptance
- a1
- a2

## Hand-off
to dev-1.
"""
    spec = extract_spec(raw)
    md = spec.to_markdown()
    assert "## Rationale" in md
    assert "## Acceptance" in md
    assert "## Hand-off" in md
    assert "r1" in md and "a1" in md and "dev-1" in md
