from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .contract_gate import Decision, decide_discord_action, decide_mcp_tool

_TUTORING_INTENT = re.compile(
    r"\b(teach|tutor(?:ing)?|explain|deep[\s-]?dive|lesson)\b",
    re.IGNORECASE,
)
_TASK_MANAGEMENT = re.compile(
    r"\b("
    r"(?:add|list|complete|delete|manage)\s+tasks?"
    r"|tasks?\s*:"
    r"|todo(?:s)?"
    r")\b",
    re.IGNORECASE,
)
_TASK_WORD = re.compile(r"\btasks?\b", re.IGNORECASE)


@dataclass(frozen=True)
class DiscordMessage:
    channel_id: str
    author_id: str
    mentions: list[str]
    content: str


@dataclass(frozen=True)
class DiscordRoute:
    ignored: bool
    persona_id: str | None = None
    decision: Decision | None = None
    reason: str | None = None
    hint_persona: str | None = None


def _infer_action(persona_id: str, content: str) -> str:
    # Precedence:
    # 1) explicit task-management phrasing (so Tutor can refuse + hint)
    # 2) Tutor bot identity / tutoring intent
    # 3) bare "task(s)" word for Assistant-style routing
    # 4) default digest
    if _TASK_MANAGEMENT.search(content):
        return "manage_tasks"
    if persona_id == "tutor":
        return "conduct_tutoring"
    if _TUTORING_INTENT.search(content):
        return "conduct_tutoring"
    if _TASK_WORD.search(content):
        return "manage_tasks"
    return "compose_digest"


def route_discord_message(
    message: DiscordMessage,
    home_channel_id: str,
    allowed_users: set[str],
) -> DiscordRoute:
    if message.channel_id != home_channel_id:
        return DiscordRoute(ignored=True)
    if message.author_id not in allowed_users:
        return DiscordRoute(ignored=True)
    if not message.mentions:
        return DiscordRoute(ignored=True)

    persona_id = message.mentions[0].strip().lower()
    action = _infer_action(persona_id, message.content)
    result = decide_discord_action(persona_id, action)
    return DiscordRoute(
        ignored=False,
        persona_id=persona_id,
        decision=result.decision,
        reason=result.reason,
        hint_persona=result.hint_persona,
    )


def route_mcp_tool(tool_name: str, misuse_count: int = 0) -> dict[str, Any]:
    result = decide_mcp_tool(tool_name, misuse_count=misuse_count)
    if result.decision == Decision.ALLOW:
        return {
            "ok": True,
            "tool": tool_name,
            "data": {},
            "warnings": [],
            "errors": [],
        }
    return {
        "ok": False,
        "tool": tool_name,
        "data": {},
        "warnings": [],
        "errors": [
            {
                "code": "OUT_OF_SCOPE",
                "surface": "mcp",
                "message": result.reason,
            }
        ],
        "systemic_escalation": result.systemic_escalation,
    }
