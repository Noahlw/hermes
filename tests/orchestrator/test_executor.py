"""Tests for orchestrator.executor."""

from pathlib import Path

from orchestrator.executor import DISPATCH_PROMPT_TEMPLATE, comment_status, dispatch_agent


def test_dispatch_prompt_template_includes_ticket_and_plan():
    prompt = DISPATCH_PROMPT_TEMPLATE.format(
        repo="Noahlw/hermes",
        ticket_number=42,
        plan_path="/tmp/foo.md",
    )
    assert "/issues/42" in prompt
    assert "/tmp/foo.md" in prompt


def test_dispatch_agent_dry_run():
    sid = dispatch_agent(99, Path("/tmp/x.md"), dry_run=True)
    assert sid == "dry-run-99"


def test_dispatch_agent_invokes_gh(mocker):
    fake = mocker.Mock()
    fake.stdout = "agent-session-xyz\n"
    fake.returncode = 0
    runner = mocker.patch("orchestrator.executor.subprocess.run", return_value=fake)
    sid = dispatch_agent(7, Path("/tmp/p.md"), dry_run=False)
    assert sid == "agent-session-xyz"
    runner.assert_called_once()
    cmd = runner.call_args[0][0]
    assert cmd[0:3] == ["gh", "agent-task", "create"]


def test_comment_status_invokes_gh(mocker):
    runner = mocker.patch("orchestrator.executor.subprocess.run")
    comment_status(7, "hello")
    cmd = runner.call_args[0][0]
    assert cmd[0:3] == ["gh", "issue", "comment"]
    assert "7" in cmd
    assert "hello" in cmd[-1]
