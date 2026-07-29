from __future__ import annotations

import enum
import json
import types
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any


class Decision(str, enum.Enum):
    ALLOW = "allow"
    REFUSE_DISCORD = "refuse_discord"
    MCP_OOS = "mcp_oos"


@dataclass(frozen=True)
class GateResult:
    decision: Decision
    reason: str
    hint_persona: str | None = None
    systemic_escalation: bool = False


# Cross-cutting deployment policy — not derivable from persona contracts.
V1_OOS_ACTIONS: frozenset[str] = frozenset(
    {"generate_plan", "execute_plan", "push_plan_pr"}
)


@dataclass(frozen=True)
class ContractData:
    """Loaded and validated contract data that drives gate decisions."""

    all_personas: frozenset[str]
    discord_personas: frozenset[str]
    librarian_jobs: frozenset[str]
    researcher_jobs: frozenset[str]
    mcp_allowed_jobs: frozenset[str]
    # Read-only mappings. Wrapped in MappingProxyType so the cached
    # ContractData singleton cannot be mutated by callers.
    persona_actions: Mapping[str, frozenset[str]]
    persona_jobs: Mapping[str, frozenset[str]]


# Fixed V1 persona roster (Issue #62 US2, ADR 0003). The loader rejects
# any persona_id outside this set so unknown or user-created personas
# cannot silently enter the gate.
_ALLOWED_PERSONA_IDS: frozenset[str] = frozenset(
    {"main_agent", "librarian", "researcher", "assistant", "tutor"}
)
_ALLOWED_DISCORD_PERSONA_IDS: frozenset[str] = frozenset(
    {"main_agent", "assistant", "tutor"}
)
_ALLOWED_JOB_BACKED_PERSONA_IDS: frozenset[str] = frozenset(
    {"librarian", "researcher"}
)


_CONTRACTS_DIR = Path(__file__).resolve().parent / "contracts"


def _validate_contracts(raw: list[dict[str, Any]]) -> None:
    seen_ids: set[str] = set()
    for entry in raw:
        pid = entry.get("persona_id")
        if not isinstance(pid, str) or not pid:
            raise ValueError(f"Contract missing valid 'persona_id': {entry}")
        if pid not in _ALLOWED_PERSONA_IDS:
            raise ValueError(
                f"Contract '{pid}' is not in the fixed V1 persona roster "
                f"{sorted(_ALLOWED_PERSONA_IDS)}"
            )
        if pid in seen_ids:
            raise ValueError(f"Duplicate persona_id: {pid}")
        seen_ids.add(pid)
        if "purpose" not in entry:
            raise ValueError(f"Contract '{pid}' missing 'purpose'")
        if pid in _ALLOWED_DISCORD_PERSONA_IDS and "allowed_actions" not in entry:
            raise ValueError(
                f"Contract '{pid}' is Discord-reachable and must declare 'allowed_actions'"
            )
        if pid in _ALLOWED_JOB_BACKED_PERSONA_IDS and "allowed_jobs" not in entry:
            raise ValueError(
                f"Contract '{pid}' is job-backed and must declare 'allowed_jobs'"
            )
        has_actions = "allowed_actions" in entry
        has_jobs = "allowed_jobs" in entry
        if not has_actions and not has_jobs:
            raise ValueError(
                f"Contract '{pid}' must have 'allowed_actions' or 'allowed_jobs'"
            )
        if pid in _ALLOWED_DISCORD_PERSONA_IDS and has_jobs:
            raise ValueError(
                f"Contract '{pid}' is Discord-reachable and must not declare 'allowed_jobs'"
            )
        if pid in _ALLOWED_JOB_BACKED_PERSONA_IDS and has_actions:
            raise ValueError(
                f"Contract '{pid}' is job-backed and must not declare 'allowed_actions'"
            )
        if has_actions and len(entry["allowed_actions"]) == 0:
            raise ValueError(f"Contract '{pid}' allowed_actions is empty")
        if has_jobs and len(entry["allowed_jobs"]) == 0:
            raise ValueError(f"Contract '{pid}' allowed_jobs is empty")
        if has_actions:
            if not isinstance(entry["allowed_actions"], list):
                raise ValueError(
                    f"Contract '{pid}' allowed_actions is not a list: {entry['allowed_actions']}"
                )
            for a in entry["allowed_actions"]:
                if not isinstance(a, str):
                    raise TypeError(
                        f"Contract '{pid}' allowed_actions item not a string: {a}"
                    )
        if has_jobs:
            if not isinstance(entry["allowed_jobs"], list):
                raise ValueError(
                    f"Contract '{pid}' allowed_jobs is not a list: {entry['allowed_jobs']}"
                )
            for j in entry["allowed_jobs"]:
                if not isinstance(j, str):
                    raise TypeError(
                        f"Contract '{pid}' allowed_jobs item not a string: {j}"
                    )


@cache
def load_contracts() -> ContractData:
    """Load and validate persona contracts from disk.

    Explicit cached loader — not import-time — so tests can control
    the contract directory and imports never fail on missing files.
    """
    raw: list[dict[str, Any]] = []
    for path in sorted(_CONTRACTS_DIR.glob("*.json")):
        with open(path) as f:
            raw.append(json.load(f))
    _validate_contracts(raw)

    all_personas: set[str] = set()
    discord_personas: set[str] = set()
    librarian_jobs: set[str] = set()
    researcher_jobs: set[str] = set()
    persona_actions: dict[str, frozenset[str]] = {}
    persona_jobs: dict[str, frozenset[str]] = {}

    for entry in raw:
        pid = entry["persona_id"]
        all_personas.add(pid)
        if "allowed_actions" in entry:
            discord_personas.add(pid)
            persona_actions[pid] = frozenset(entry["allowed_actions"])
        if "allowed_jobs" in entry:
            persona_jobs[pid] = frozenset(entry["allowed_jobs"])
        if pid == "librarian" and "allowed_jobs" in entry:
            librarian_jobs.update(entry["allowed_jobs"])
        if pid == "researcher" and "allowed_jobs" in entry:
            researcher_jobs.update(entry["allowed_jobs"])

    return ContractData(
        all_personas=frozenset(all_personas),
        discord_personas=frozenset(discord_personas),
        librarian_jobs=frozenset(librarian_jobs),
        researcher_jobs=frozenset(researcher_jobs),
        mcp_allowed_jobs=frozenset(librarian_jobs | researcher_jobs),
        persona_actions=types.MappingProxyType(dict(persona_actions)),
        persona_jobs=types.MappingProxyType(dict(persona_jobs)),
    )


def _get_contracts() -> ContractData:
    """Thin accessor — overridable in tests via dependency injection."""
    return load_contracts()


def decide_discord_action(persona_id: str, action: str) -> GateResult:
    contracts = _get_contracts()
    persona = persona_id.strip().lower()
    if persona not in contracts.all_personas:
        return GateResult(Decision.REFUSE_DISCORD, "unknown persona")
    if persona not in contracts.discord_personas:
        return GateResult(
            Decision.REFUSE_DISCORD,
            "persona is not Discord-reachable",
        )
    if action in V1_OOS_ACTIONS:
        return GateResult(Decision.REFUSE_DISCORD, "plan/execute is out of V1 scope")

    # Check if this persona allows the action in its contract
    persona_allowed = contracts.persona_actions.get(persona, frozenset())
    if action in persona_allowed:
        return GateResult(Decision.ALLOW, f"{persona} allows action")

    # Persona does not list this action — refuse with a hint to a more
    # appropriate persona when one can be determined.
    hint = _suggest_persona(action, contracts)
    return GateResult(
        Decision.REFUSE_DISCORD,
        f"action not allowed for {persona}",
        hint_persona=hint,
    )


def _suggest_persona(action: str, contracts: ContractData) -> str | None:
    """Suggest a persona that *does* allow this action, or None."""
    # Specialists win over main_agent. Order is fixed so the tie-break
    # is deterministic; the contract loader restricts the roster to the
    # fixed V1 set, so unknown persona_ids are impossible.
    specialist_order = ("assistant", "tutor")
    for pid in specialist_order:
        if action in contracts.persona_actions.get(pid, frozenset()):
            return pid
    if action in contracts.persona_actions.get("main_agent", frozenset()):
        return "main_agent"
    for pid in specialist_order:
        if action in contracts.persona_jobs.get(pid, frozenset()):
            return pid
    for pid, jobs in contracts.persona_jobs.items():
        if action in jobs:
            return pid
    return None


def decide_mcp_tool(tool_name: str, misuse_count: int = 0) -> GateResult:
    contracts = _get_contracts()
    tool = tool_name.strip().lower()
    if tool in contracts.mcp_allowed_jobs:
        return GateResult(Decision.ALLOW, "tool is in coding-agent information suite")
    reason = "tool is out of coding-agent MCP scope"
    return GateResult(
        Decision.MCP_OOS,
        reason,
        systemic_escalation=misuse_count >= 3,
    )
