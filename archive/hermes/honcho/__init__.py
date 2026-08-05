"""Honcho workspace isolation for V1 personas (Ticket 73).

Verifies that the five hermes-agent profiles use distinct Honcho
backend workspaces and distinct peer identities, and that cross-profile
memory reads are blocked at the configuration level.
"""

from hermes.honcho.isolation import (
    HonchoWorkspaceConfig,
    WorkspaceIsolationReport,
    check_isolation,
    resolve_workspace_configs,
)

__all__: tuple[str, ...] = (
    "HonchoWorkspaceConfig",
    "WorkspaceIsolationReport",
    "check_isolation",
    "resolve_workspace_configs",
)
