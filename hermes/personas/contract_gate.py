from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional


class Decision(str, enum.Enum):
    ALLOW = "allow"
    REFUSE_DISCORD = "refuse_discord"
    MCP_OOS = "mcp_oos"


@dataclass(frozen=True)
class GateResult:
    decision: Decision
    reason: str
    hint_persona: Optional[str] = None
    systemic_escalation: bool = False


DISCORD_PERSONAS = {"assistant", "tutor", "main_agent"}
ALL_PERSONAS = DISCORD_PERSONAS | {"librarian", "researcher", "developer"}

LIBRARIAN_JOBS = {
    "library_search",
    "session_brief",
    "knowledge_catalog",
    "expand_citation",
    "impact_map",
}
RESEARCHER_JOBS = {"conduct_research"}
MCP_ALLOWED_JOBS = LIBRARIAN_JOBS | RESEARCHER_JOBS
V1_OOS_ACTIONS = {"generate_plan", "execute_plan", "push_plan_pr"}


def decide_discord_action(persona_id: str, action: str) -> GateResult:
    persona = persona_id.strip().lower()
    if persona not in ALL_PERSONAS:
        return GateResult(Decision.REFUSE_DISCORD, "unknown persona")
    if persona in {"librarian", "researcher", "developer"}:
        return GateResult(Decision.REFUSE_DISCORD, "persona is not Discord-reachable")
    if action in V1_OOS_ACTIONS:
        return GateResult(Decision.REFUSE_DISCORD, "plan/execute is out of V1 scope")
    if persona == "assistant" and action == "conduct_tutoring":
        return GateResult(
            Decision.REFUSE_DISCORD,
            "assistant cannot run deep-dive tutoring",
            hint_persona="tutor",
        )
    if persona == "tutor" and action == "manage_tasks":
        return GateResult(
            Decision.REFUSE_DISCORD,
            "tutor cannot manage tasks",
            hint_persona="assistant",
        )
    if persona == "main_agent":
        if action in {"manage_tasks", "conduct_tutoring", "run_ops_digest", "compose_digest"} or action in MCP_ALLOWED_JOBS:
            return GateResult(Decision.ALLOW, "main agent super-set allows action")
        return GateResult(Decision.REFUSE_DISCORD, "action not allowed for main agent")
    if persona == "assistant":
        if action in {"manage_tasks", "compose_digest"} or action in MCP_ALLOWED_JOBS:
            return GateResult(Decision.ALLOW, "assistant allows action")
        return GateResult(Decision.REFUSE_DISCORD, "action not allowed for assistant")
    if persona == "tutor":
        if action == "conduct_tutoring" or action in MCP_ALLOWED_JOBS:
            return GateResult(Decision.ALLOW, "tutor allows action")
        return GateResult(Decision.REFUSE_DISCORD, "action not allowed for tutor")
    return GateResult(Decision.REFUSE_DISCORD, "action denied")


def decide_mcp_tool(tool_name: str, misuse_count: int = 0) -> GateResult:
    tool = tool_name.strip().lower()
    if tool in MCP_ALLOWED_JOBS:
        return GateResult(Decision.ALLOW, "tool is in coding-agent information suite")
    reason = "tool is out of coding-agent MCP scope"
    return GateResult(
        Decision.MCP_OOS,
        reason,
        systemic_escalation=misuse_count >= 3,
    )
