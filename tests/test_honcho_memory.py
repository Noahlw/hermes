"""Honcho memory wiring contract tests — policy-side resolution + naming.

The runtime client (hermes_agent.honcho_client) is exercised live against the
VM in the acceptance smoke; here we pin the two pure contracts the gateway
depends on: workspace resolution from hermes.honcho.isolation and the
hermes_<persona> naming convention that honcho-workspaces.py provisions.
"""

from __future__ import annotations

from hermes.honcho.isolation import resolve_workspace_configs

EXPECTED_PERSONAS = {"main_agent", "assistant", "tutor", "librarian", "researcher"}


def test_resolve_workspace_configs_covers_all_personas() -> None:
    configs = resolve_workspace_configs()
    assert set(configs) == EXPECTED_PERSONAS


def test_workspace_names_are_hermes_prefixed() -> None:
    configs = resolve_workspace_configs()
    names = {c.workspace_id for c in configs.values()}
    assert all(n.startswith("hermes_") for n in names)
    assert names == {f"hermes_{p}" for p in EXPECTED_PERSONAS}


def test_ai_peer_id_matches_workspace_suffix() -> None:
    configs = resolve_workspace_configs()
    for c in configs.values():
        # honcho-workspaces.py provisions peer = workspace = hermes_<persona>.
        assert c.ai_peer == c.workspace_id == f"hermes_{c.persona_id}"


def test_runtime_naming_helper_matches_provisioner() -> None:
    """hermes_agent.honcho_client must reuse the same name derivation as
    setup/honcho-workspaces.py (which reads PROFILE_DEFINITIONS)."""
    from hermes.profiles.config import PROFILE_DEFINITIONS

    import hermes_agent.honcho_client as hc

    for persona_id in PROFILE_DEFINITIONS:
        assert hc.persona_workspace_name(persona_id) == f"hermes_{persona_id}"
