"""Orchestrator: closure-listener for wayfinder planning closes.

Polls `gh issue list` for planning tickets that have closed, filters out ones
already logged in `state_file`, and yields structured `ClosedPlanningTicket`
records for downstream spec extraction and impl-ticket spawning.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class ClosedPlanningTicket:
    """A wayfinder planning ticket that has closed on GitHub."""
    number: int
    title: str
    body: str
    spec_text: str
    closed_at: datetime


class ClosureListener:
    """Poll `gh` for newly-closed planning tickets."""

    def __init__(self, repo: str, state_file: Path, gh_bin: str = "gh") -> None:
        self.repo = repo
        self.state_file = state_file
        self.gh_bin = gh_bin

    def _load_processed(self) -> dict[str, str]:
        if not self.state_file.exists():
            return {}
        try:
            return json.loads(self.state_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_processed(self, processed: dict[str, str]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(processed, indent=2, sort_keys=True))

    def _gh_list_closed(self) -> list[dict]:
        cmd = [
            self.gh_bin, "issue", "list",
            "--repo", self.repo,
            "--state", "closed",
            "--label", "phase:planning",
            "--json", "number,title,body,closedAt,comments",
            "--limit", "200",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout) if result.stdout.strip() else []
        return data if isinstance(data, list) else []

    @staticmethod
    def _last_comment_body(comments_blob) -> str:
        """The last comment on the ticket, or empty string if no comments."""
        if not comments_blob:
            return ""
        if isinstance(comments_blob, dict):
            nodes = comments_blob.get("nodes") or []
        elif isinstance(comments_blob, list):
            nodes = comments_blob
        else:
            return ""
        if not nodes:
            return ""
        return str(nodes[-1].get("body", ""))

    def fetch_new_planning_closes(self) -> list[ClosedPlanningTicket]:
        processed = self._load_processed()
        rows = self._gh_list_closed()
        out: list[ClosedPlanningTicket] = []
        for row in rows:
            number = int(row.get("number", 0))
            if not number:
                continue
            key = str(number)
            if key in processed:
                continue
            closed_at_str = row.get("closedAt") or ""
            try:
                closed_at = datetime.fromisoformat(closed_at_str.replace("Z", "+00:00").replace("+00:00", ""))
            except ValueError:
                closed_at = datetime.now()
            spec_text = self._last_comment_body(row.get("comments"))
            out.append(
                ClosedPlanningTicket(
                    number=number,
                    title=row.get("title", ""),
                    body=row.get("body", ""),
                    spec_text=spec_text,
                    closed_at=closed_at,
                )
            )
        return out

    def mark_processed(self, tickets: list[ClosedPlanningTicket]) -> None:
        processed = self._load_processed()
        for t in tickets:
            processed[str(t.number)] = t.closed_at.isoformat()
        self._save_processed(processed)


def main() -> Iterator[ClosedPlanningTicket]:
    """CLI: print new planning closes to stdout, one per line as JSON."""
    import os
    repo = os.environ.get("HERMES_REPO", "Noahlw/hermes")
    state_file = Path(os.environ.get("HERMES_STATE_FILE", "orchestrator/state/processed.json"))
    listener = ClosureListener(repo=repo, state_file=state_file)
    new = listener.fetch_new_planning_closes()
    for t in new:
        yield t
    listener.mark_processed(new)


if __name__ == "__main__":
    import sys
    for ticket in main():
        print(json.dumps({
            "number": ticket.number,
            "title": ticket.title,
            "spec_text": ticket.spec_text,
            "closed_at": ticket.closed_at.isoformat(),
        }))
        sys.stdout.flush()
