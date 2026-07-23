"""Orchestrator: agent dispatcher.

Sends a sub-agent to execute one implementation ticket. The agent runs
the writing-plans-style plan that was saved at `plan_path`. The agent
comments status on the issue, then closes it when done.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


DISPATCH_PROMPT_TEMPLATE = """You are the implementer for https://github.com/{repo}/issues/{ticket_number}.
The full plan is at {plan_path}.
Follow the writing-plans conventions strictly: failing test first, minimal impl, TDD, frequent commits.
Do NOT modify the closed planning ticket.
Do NOT touch other orchestrator files.
Close the implementation ticket when all acceptance artifacts are produced.
"""


def dispatch_agent(
    ticket_number: int,
    plan_path: Path,
    repo: str = "Noahlw/hermes",
    gh_bin: str = "gh",
    dry_run: bool = False,
) -> str:
    """Dispatch a fresh subagent. Returns the session id from the runner.

    Implementation shells out to `gh agent-task` (or `claude` / `codex` if
    available) — kept abstract so the orchestrator can be deployed against
    any runner. For the dry-run path we return a synthetic id.
    """
    if dry_run:
        return f"dry-run-{ticket_number}"

    prompt = DISPATCH_PROMPT_TEMPLATE.format(
        repo=repo,
        ticket_number=ticket_number,
        plan_path=str(plan_path),
    )

    # `gh agent-task create` is the GitHub-native way. We invoke it and
    # capture the agent's session id from stdout.
    cmd = [
        gh_bin, "agent-task", "create",
        "--repo", repo,
        "--issue", str(ticket_number),
        "--prompt", prompt,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return (result.stdout or "").strip().splitlines()[-1] or "unknown"


def comment_status(impl_ticket_number: int, message: str, repo: str = "Noahlw/hermes", gh_bin: str = "gh") -> None:
    """Post a status comment to the impl ticket."""
    cmd = [
        gh_bin, "issue", "comment", str(impl_ticket_number),
        "--repo", repo,
        "--body", message,
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
