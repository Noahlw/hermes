"""Deterministic ops digest formatter.

Produces a ≤200-token daily summary from cron job status data.  No
model call — the output is a mechanical format over structured input.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field


class CronJobStatus(str, enum.Enum):
    HEALTHY = "healthy"
    FAILED = "failed"
    STALE = "stale"
    NEVER_RUN = "never_run"


@dataclass(frozen=True)
class DigestEntry:
    """Status line for one cron job."""

    job_id: str
    job_name: str
    status: CronJobStatus
    details: str = ""

    @property
    def status_icon(self) -> str:
        icons = {
            CronJobStatus.HEALTHY: "✅",
            CronJobStatus.FAILED: "❌",
            CronJobStatus.STALE: "⚠️",
            CronJobStatus.NEVER_RUN: "🔹",
        }
        return icons[self.status]


def _simple_token_count(text: str) -> int:
    """Approximate token count for plain English prose.

    Heuristic: split on whitespace; count 1 token per word, +1 for each
    newline-separated line (paragraph break overhead).  This is
    intentionally simple — a ≤200-token budget leaves plenty of margin
    vs the ~3-char/token average, so an exact tokenizer is overkill.
    """
    words = text.split()
    lines = text.count("\n")
    return len(words) + lines


def token_count(digest_text: str) -> int:
    """Public token count for the digest prose."""
    return _simple_token_count(digest_text)


def format_digest_markdown(
    entries: list[DigestEntry],
    window_start: str = "",
    window_end: str = "",
) -> str:
    """Format digest entries as Markdown.

    Each entry gets one status line; total output stays within the
    ≤200-token "one-line status per check" budget.
    """
    max_per_entry = 200 // max(1, len(entries))
    lines: list[str] = []
    if window_start and window_end:
        lines.append(f"**Hermes Daily Ops Digest**  ({window_start} → {window_end})")
    else:
        lines.append("**Hermes Daily Ops Digest**")
    lines.append("")

    for entry in entries:
        base = f"{entry.status_icon} **{entry.job_name}** — {entry.status.value}"
        if entry.details:
            detail = entry.details
            # Truncate details to fit the per-entry budget.
            if _simple_token_count(base + " " + detail) > max_per_entry:
                detail = detail[: max_per_entry * 5]  # rough char limit
                detail = detail.rsplit(" ", 1)[0] + "…"
            base += f" — {detail}"
        lines.append(base)

    return "\n".join(lines)


def format_digest(
    entries: list[DigestEntry],
    window_start: str = "",
    window_end: str = "",
) -> DigestEntry:
    """Format the digest.

    Returns the digest as a DigestEntry container with the Markdown
    summary and structured per-job status.  Per-entry truncation in
    format_digest_markdown enforces the ≤200-token budget.
    """
    markdown = format_digest_markdown(entries, window_start, window_end)

    per_job = [
        {
            "job_id": e.job_id,
            "job_name": e.job_name,
            "status": e.status.value,
            "details": e.details,
        }
        for e in entries
    ]
    return DigestEntry(
        job_id="ops-digest",
        job_name="Daily Ops Digest",
        status=CronJobStatus.HEALTHY,
        details=json.dumps(
            {"summary_markdown": markdown, "per_job_status": per_job}
        ),
    )


def format_digest_for_db(
    entries: list[DigestEntry],
    window_start: str = "",
    window_end: str = "",
) -> tuple[str, str, list[dict[str, str]]]:
    """Format the digest and return DB-ready fields.

    Returns (summary_markdown, per_job_status_json, per_job_list).
    """
    result = format_digest(entries, window_start, window_end)
    data = json.loads(result.details)
    return (
        data["summary_markdown"],
        json.dumps(data["per_job_status"], indent=2),
        data["per_job_status"],
    )
