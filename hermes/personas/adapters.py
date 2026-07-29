from __future__ import annotations

import re
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Any

from .contract_gate import (
    Decision,
    decide_discord_action,
    decide_mcp_tool,
    load_contracts,
)

_TUTORING_INTENT = re.compile(
    r"\b(teach|tutor(?:ing)?|explain|deep[\s-]?dive|lesson)\b",
    re.IGNORECASE,
)
_TASK_MANAGEMENT = re.compile(
    r"\b("
    r"(?:add|list|complete|delete|manage)\s+(?:my\s+|a\s+|the\s+)?(?:tasks?|todos?)"
    r"|(?:tasks?|todos?)\s*:"
    r")\b",
    re.IGNORECASE,
)
_DELETE_INTENT = re.compile(
    r"\bdelete\s+(?:my\s+|a\s+|the\s+|this\s+|these\s+|those\s+|all\s+|every\s+|completed\s+)?(?:tasks?|todos?)\b"
    r"|\b(?:remove|wipe|clear|destroy)\s+(?:my\s+|a\s+|the\s+|this\s+|these\s+|those\s+|all\s+|every\s+|completed\s+)?(?:tasks?|todos?)\b",
    re.IGNORECASE,
)
_TASK_WORD = re.compile(r"\b(tasks?|todos?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class DiscordMessage:
    channel_id: str
    author_id: str
    mentions: tuple[str, ...]
    content: str
    confirm_delete: bool = False


@dataclass(frozen=True)
class DiscordRoute:
    ignored: bool
    persona_id: str | None = None
    decision: Decision | None = None
    reason: str | None = None
    hint_persona: str | None = None
    confirm_required: bool = False


def _strip_addressed_mention(content: str) -> str:
    # Drop the leading ``@persona`` token so the classifier doesn't
    # bias on the bot identity itself (e.g. ``_TUTORING_INTENT`` would
    # match "tutor" inside ``@tutor`` and turn every tutor-bot message
    # into ``conduct_tutoring``). The addressed mention is already
    # resolved by ``route_discord_message`` before this is called,
    # so the strip is purely cosmetic for the classifier — it does
    # not change *who* the message is addressed to.
    # Only a single leading token, optionally preceded by whitespace,
    # so ordinary prose like "send mail to user@example.com" is left alone.
    match = re.match(r"^\s*@\S+", content)
    return content[match.end():] if match else content


def _infer_action(persona_id: str, content: str) -> str:
    # Precedence:
    # 1) tutoring intent (so "teach me about todos/tasks" refuses on Assistant)
    # 2) explicit task-management phrasing (so Tutor can refuse + hint)
    # 3) Tutor bot identity default
    # 4) bare task/todo word for Assistant-style routing
    # 5) default digest
    body = _strip_addressed_mention(content)
    if _TUTORING_INTENT.search(body):
        return "conduct_tutoring"
    if _TASK_MANAGEMENT.search(body):
        return "manage_tasks"
    if persona_id == "tutor":
        return "conduct_tutoring"
    if _TASK_WORD.search(body):
        return "manage_tasks"
    return "compose_digest"


def route_discord_message(
    message: DiscordMessage,
    home_channel_id: str,
    allowed_users: AbstractSet[str],
) -> DiscordRoute:
    if message.channel_id != home_channel_id:
        return DiscordRoute(ignored=True)
    if message.author_id not in allowed_users:
        return DiscordRoute(ignored=True)
    if not message.mentions:
        return DiscordRoute(ignored=True)

    persona_id = message.mentions[0].strip().lower()
    action = _infer_action(persona_id, message.content)

    # confirm_delete check: only applies to personas that actually have
    # manage_tasks in their contract.  For personas where the action is
    # itself out of scope (e.g. Tutor asked to delete tasks), the gate
    # refusal takes precedence.
    contracts = load_contracts()
    persona_allowed = contracts.persona_actions.get(persona_id, frozenset())
    can_manage_tasks = "manage_tasks" in persona_allowed
    if can_manage_tasks and action == "manage_tasks" and _DELETE_INTENT.search(message.content) and not message.confirm_delete:
            return DiscordRoute(
                ignored=False,
                persona_id=persona_id,
                decision=Decision.REFUSE_DISCORD,
                reason="task deletion requires confirm_delete=True",
                confirm_required=True,
            )

    result = decide_discord_action(persona_id, action)
    return DiscordRoute(
        ignored=False,
        persona_id=persona_id,
        decision=result.decision,
        reason=result.reason,
        hint_persona=result.hint_persona,
    )


def _resolve_job_persona(tool_name: str) -> str | None:
    """Map an MCP tool name to its owning job-backed persona."""
    # Normalize the same way decide_mcp_tool() does so the gate's
    # uppercase/whitespace tolerance lines up with the dispatch lookup.
    normalized = tool_name.strip().lower()
    contracts = load_contracts()
    if normalized in contracts.librarian_jobs:
        return "librarian"
    if normalized in contracts.researcher_jobs:
        return "researcher"
    return None


def route_mcp_tool(tool_name: str, misuse_count: int = 0) -> dict[str, Any]:
    result = decide_mcp_tool(tool_name, misuse_count=misuse_count)
    if result.decision == Decision.ALLOW:
        return {
            "ok": True,
            "tool": tool_name,
            "job_persona": _resolve_job_persona(tool_name),
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


__all__: tuple[str, ...] = (
    "Decision",
    "DiscordMessage",
    "DiscordRoute",
    "decide_discord_action",
    "decide_mcp_tool",
    "load_contracts",
    "route_discord_message",
    "route_mcp_tool",
)
