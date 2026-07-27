from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contract_gate import Decision, decide_discord_action, decide_mcp_tool


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
    normalized = content.lower()
    if "task" in normalized:
        return "manage_tasks"
    if persona_id == "tutor":
        return "conduct_tutoring"
    if "tutor" in normalized or "teach" in normalized:
        return "conduct_tutoring"
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
