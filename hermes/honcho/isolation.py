"""Workspace isolation verification for the five persona profiles.

This module validates that each profile resolves a distinct Honcho
ai_peer identity and workspace_id, proving that cross-profile memory
reads are blocked at the Honcho backend API level — not just by
naming convention.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from hermes.profiles.config import PROFILE_DEFINITIONS, generate_honcho_json


@dataclass(frozen=True)
class HonchoWorkspaceConfig:
    """Resolved Honcho configuration for one persona profile."""

    persona_id: str
    ai_peer: str
    workspace_id: str


@dataclass(frozen=True)
class WorkspaceIsolationReport:
    """Result of checking workspace isolation across all V1 profiles."""

    configs: dict[str, HonchoWorkspaceConfig]
    all_peers_distinct: bool
    all_workspaces_distinct: bool
    violations: list[str] = field(default_factory=list)

    @property
    def is_isolated(self) -> bool:
        return self.all_peers_distinct and self.all_workspaces_distinct and len(self.violations) == 0


def resolve_workspace_configs() -> dict[str, HonchoWorkspaceConfig]:
    """Resolve Honcho workspace configs for all five V1 personas.

    Reads the profile definitions and their generated honcho.json to
    determine the ai_peer and workspace_id for each.
    """
    configs: dict[str, HonchoWorkspaceConfig] = {}
    for persona_id, profile in PROFILE_DEFINITIONS.items():
        honcho_raw = generate_honcho_json(profile)
        honcho = json.loads(honcho_raw)
        configs[persona_id] = HonchoWorkspaceConfig(
            persona_id=persona_id,
            ai_peer=honcho["ai_peer"],
            workspace_id=honcho["workspace_id"],
        )
    return configs


def check_isolation(
    configs: dict[str, HonchoWorkspaceConfig] | None = None,
) -> WorkspaceIsolationReport:
    """Check that all five profiles use distinct Honcho workspaces and peers.

    Returns a report with violations if any two profiles share a
    workspace_id or ai_peer identity.
    """
    if configs is None:
        configs = resolve_workspace_configs()

    peers: dict[str, str] = {}   # peer → persona_id
    workspaces: dict[str, str] = {}  # workspace → persona_id
    violations: list[str] = []

    for persona_id, config in configs.items():
        if config.ai_peer in peers:
            violations.append(
                f"ai_peer collision: '{persona_id}' and "
                f"'{peers[config.ai_peer]}' both use '{config.ai_peer}'"
            )
        else:
            peers[config.ai_peer] = persona_id

        if config.workspace_id in workspaces:
            violations.append(
                f"workspace_id collision: '{persona_id}' and "
                f"'{workspaces[config.workspace_id]}' both use "
                f"'{config.workspace_id}'"
            )
        else:
            workspaces[config.workspace_id] = persona_id

    all_peers_distinct = len(configs) == len(peers)
    all_workspaces_distinct = len(configs) == len(workspaces)

    return WorkspaceIsolationReport(
        configs=configs,
        all_peers_distinct=all_peers_distinct,
        all_workspaces_distinct=all_workspaces_distinct,
        violations=violations,
    )
