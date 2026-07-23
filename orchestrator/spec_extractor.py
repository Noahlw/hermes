"""Orchestrator: spec-extraction utility.

Parses a wayfinder planning ticket's close comment into a structured `Spec`
with three sections: Rationale, Acceptance, Hand-off. Empty sections are
preserved (the orchestrator flags them downstream).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Spec:
    """Parsed spec from a wayfinder planning-ticket close comment."""
    headline: str = ""
    rationale_bullets: list[str] = field(default_factory=list)
    acceptance_artifacts: list[str] = field(default_factory=list)
    hand_off: str = ""
    incomplete: bool = False

    def to_markdown(self) -> str:
        parts = [f"# {self.headline or 'Spec'}", ""]
        parts.append("## Rationale")
        if self.rationale_bullets:
            parts.extend(f"- {b}" for b in self.rationale_bullets)
        else:
            parts.append("- (none)")
        parts += ["", "## Acceptance", ""]
        if self.acceptance_artifacts:
            parts.extend(f"- {a}" for a in self.acceptance_artifacts)
        else:
            parts.append("- (none)")
        parts += ["", "## Hand-off", "", self.hand_off or "(none)"]
        return "\n".join(parts) + "\n"


_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _extract_section(markdown: str, name: str) -> tuple[str, int, int]:
    """Return the body of the `## <name>` section plus start/end indices."""
    pattern = re.compile(r"^##\s+" + re.escape(name) + r"\s*\n", re.MULTILINE)
    m = pattern.search(markdown)
    if not m:
        return "", -1, -1
    start = m.end()
    next_match = _SECTION_RE.search(markdown, pos=start)
    end = next_match.start() if next_match else len(markdown)
    return markdown[start:end].strip(), start, end


_BULLET_PREFIX_RE = re.compile(r"^(?:[-*]\s+|\d+[.)]\s+)(.*)$")


def _bullets_from(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = _BULLET_PREFIX_RE.match(s)
        if m:
            out.append(m.group(1).strip())
        else:
            out.append(s)
    return out


def extract_spec(markdown: str) -> Spec:
    """Parse `markdown` into a `Spec`."""
    rationale_text, _, _ = _extract_section(markdown, "Rationale")
    acceptance_text, _, _ = _extract_section(markdown, "Acceptance")
    hand_off_text, _, _ = _extract_section(markdown, "Hand-off")

    rationale = _bullets_from(rationale_text)
    acceptance = _bullets_from(acceptance_text)
    # Incomplete if any of the three sections is empty — a real spec has all three.
    incomplete = not (rationale and acceptance and hand_off_text.strip())

    return Spec(
        headline=_first_line(rationale_text) or "",
        rationale_bullets=rationale,
        acceptance_artifacts=acceptance,
        hand_off=hand_off_text,
        incomplete=incomplete,
    )


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""
