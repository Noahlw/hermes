"""Tests for orchestrator.grandmap_updater."""

from pathlib import Path

from orchestrator.grandmap_updater import (
    MAP_ISSUE,
    append_decision_to_map,
    trigger_full_rebuild,
)


def test_append_decision_dry_run(tmp_path: Path):
    state = tmp_path / "state.json"
    appended = append_decision_to_map(42, "wired grandmap", state, dry_run=True)
    assert appended is True
    assert '"42"' in state.read_text()


def test_append_decision_idempotent(tmp_path: Path, mocker):
    runner = mocker.patch("orchestrator.grandmap_updater.subprocess.run")
    state = tmp_path / "state.json"

    appended1 = append_decision_to_map(7, "first call", state, dry_run=False)
    appended2 = append_decision_to_map(7, "second call", state, dry_run=False)

    assert appended1 is True
    assert appended2 is False
    runner.assert_called_once()


def test_append_decision_invokes_gh(mocker, tmp_path: Path):
    state = tmp_path / "state.json"
    runner = mocker.patch("orchestrator.grandmap_updater.subprocess.run")
    append_decision_to_map(8, "gist", state, dry_run=False)
    cmd = runner.call_args[0][0]
    assert cmd[0:2] == ["gh", "issue"]
    assert str(MAP_ISSUE) in cmd


def test_trigger_full_rebuild_dry_run(mocker):
    runner = mocker.patch("orchestrator.grandmap_updater.subprocess.run")
    n = trigger_full_rebuild(dry_run=True)
    assert n == 0
    runner.assert_not_called()


def test_trigger_full_rebuild_invokes_gh(mocker):
    runner = mocker.patch("orchestrator.grandmap_updater.subprocess.run")
    trigger_full_rebuild(dry_run=False)
    cmd = runner.call_args[0][0]
    assert cmd[0:2] == ["gh", "issue"]
    assert "comment" in cmd
