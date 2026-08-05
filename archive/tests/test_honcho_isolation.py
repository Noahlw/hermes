"""Tests for Honcho workspace isolation (Ticket 73)."""

from __future__ import annotations

import unittest

from hermes.honcho.isolation import (
    HonchoWorkspaceConfig,
    WorkspaceIsolationReport,
    check_isolation,
    resolve_workspace_configs,
)


class HonchoWorkspaceIsolationTests(unittest.TestCase):
    """Tests for workspace isolation across the five V1 personas."""

    def test_all_five_configs_resolved(self) -> None:
        configs = resolve_workspace_configs()
        self.assertEqual(
            frozenset(configs),
            frozenset({"main_agent", "librarian", "researcher", "assistant", "tutor"}),
        )

    def test_all_five_peers_are_distinct(self) -> None:
        configs = resolve_workspace_configs()
        peers = {c.ai_peer for c in configs.values()}
        self.assertEqual(len(peers), 5, f"Non-distinct peers: {peers}")

    def test_all_five_workspaces_are_distinct(self) -> None:
        configs = resolve_workspace_configs()
        workspaces = {c.workspace_id for c in configs.values()}
        self.assertEqual(len(workspaces), 5, f"Non-distinct workspaces: {workspaces}")

    def test_each_config_has_persona_specific_names(self) -> None:
        configs = resolve_workspace_configs()
        for persona_id, config in configs.items():
            self.assertIn(persona_id, config.ai_peer)
            self.assertIn(persona_id, config.workspace_id)

    def test_peer_names_not_just_the_same_string(self) -> None:
        """Acceptance: peer-name differences alone are insufficient — workspaces
        must also differ."""
        configs = resolve_workspace_configs()
        for pid, config in configs.items():
            # ai_peer and workspace_id are intentionally distinct from
            # the raw persona_id alone — they include the hermes_ prefix.
            self.assertTrue(
                config.ai_peer.startswith("hermes_"),
                f"{pid}: ai_peer '{config.ai_peer}' missing 'hermes_' prefix",
            )
            self.assertTrue(
                config.workspace_id.startswith("hermes_"),
                f"{pid}: workspace_id '{config.workspace_id}' missing 'hermes_' prefix",
            )

    def test_distinct_workspace_ids_not_just_distinct_peers(self) -> None:
        """Acceptance: workspace_id must differ even when ai_peer differs."""
        configs = resolve_workspace_configs()
        for pid, config in configs.items():
            # Each persona has its own workspace; they are not all the same
            # default workspace.
            self.assertEqual(config.workspace_id, f"hermes_{pid}")

    # --- check_isolation ---

    def test_check_isolation_passes_for_v1_roster(self) -> None:
        configs = resolve_workspace_configs()
        report = check_isolation(configs)
        self.assertTrue(report.is_isolated)
        self.assertTrue(report.all_peers_distinct)
        self.assertTrue(report.all_workspaces_distinct)
        self.assertEqual(report.violations, [])

    def test_check_isolation_detects_peer_collision(self) -> None:
        configs = {
            "main_agent": HonchoWorkspaceConfig("main_agent", "peer_a", "ws_main"),
            "assistant": HonchoWorkspaceConfig("assistant", "peer_a", "ws_asst"),
        }
        report = check_isolation(configs)
        self.assertFalse(report.is_isolated)
        self.assertFalse(report.all_peers_distinct)
        self.assertTrue(report.all_workspaces_distinct)
        self.assertGreater(len(report.violations), 0)
        self.assertTrue(any("ai_peer collision" in v for v in report.violations))

    def test_check_isolation_detects_workspace_collision(self) -> None:
        configs = {
            "main_agent": HonchoWorkspaceConfig("main_agent", "peer_a", "ws_shared"),
            "assistant": HonchoWorkspaceConfig("assistant", "peer_b", "ws_shared"),
        }
        report = check_isolation(configs)
        self.assertFalse(report.is_isolated)
        self.assertTrue(report.all_peers_distinct)
        self.assertFalse(report.all_workspaces_distinct)
        self.assertGreater(len(report.violations), 0)
        self.assertTrue(any("workspace_id collision" in v for v in report.violations))

    def test_check_isolation_detects_both_collisions(self) -> None:
        configs = {
            "main_agent": HonchoWorkspaceConfig("main_agent", "peer_a", "ws_a"),
            "assistant": HonchoWorkspaceConfig("assistant", "peer_a", "ws_a"),
        }
        report = check_isolation(configs)
        self.assertFalse(report.is_isolated)
        self.assertEqual(len(report.violations), 2)

    def test_check_isolation_empty_configs_passes(self) -> None:
        report = check_isolation({})
        self.assertTrue(report.is_isolated)
        self.assertEqual(report.violations, [])

    def test_check_isolation_single_config_passes(self) -> None:
        configs = {
            "main_agent": HonchoWorkspaceConfig("main_agent", "peer_a", "ws_a"),
        }
        report = check_isolation(configs)
        self.assertTrue(report.is_isolated)

    def test_report_properties_on_isolated_config(self) -> None:
        configs = resolve_workspace_configs()
        report = check_isolation(configs)
        self.assertTrue(report.is_isolated)
        self.assertTrue(report.all_peers_distinct)
        self.assertTrue(report.all_workspaces_distinct)
        # Each config maps back to its persona_id
        for pid in configs:
            self.assertEqual(report.configs[pid].persona_id, pid)

    # --- WorkspaceIsolationReport ---

    def test_report_defaults_to_isolated(self) -> None:
        report = WorkspaceIsolationReport(
            configs={},
            all_peers_distinct=True,
            all_workspaces_distinct=True,
        )
        self.assertTrue(report.is_isolated)

    def test_report_with_violations_is_not_isolated(self) -> None:
        report = WorkspaceIsolationReport(
            configs={},
            all_peers_distinct=True,
            all_workspaces_distinct=True,
            violations=["ai_peer collision: ..."],
        )
        self.assertFalse(report.is_isolated)

    # --- Acceptance: behavior check from #73 ---

    def test_cross_profile_reads_are_impossible_config_level(self) -> None:
        """Acceptance: different profiles resolve different workspace_ids,
        meaning Honcho context() calls from one profile cannot read
        messages stored under another profile's workspace."""
        configs = resolve_workspace_configs()
        # Every pair has distinct workspace_id
        ids = list(configs.values())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                self.assertNotEqual(
                    ids[i].workspace_id,
                    ids[j].workspace_id,
                    f"{ids[i].persona_id} and {ids[j].persona_id} share "
                    f"workspace '{ids[i].workspace_id}' — cross-read possible",
                )
                self.assertNotEqual(
                    ids[i].ai_peer,
                    ids[j].ai_peer,
                    f"{ids[i].persona_id} and {ids[j].persona_id} share "
                    f"peer '{ids[i].ai_peer}'",
                )

    def test_same_profile_retains_own_workspace(self) -> None:
        """Acceptance: a profile resolves its own workspace consistently,
        proving isolation did not disable same-profile persistence."""
        configs = resolve_workspace_configs()
        for pid, config in configs.items():
            self.assertEqual(config.ai_peer, f"hermes_{pid}")
            self.assertEqual(config.workspace_id, f"hermes_{pid}")

    def test_mcp_profiles_also_isolated(self) -> None:
        """Acceptance: Librarian and Researcher also have distinct workspaces,
        not just the Discord profiles."""
        configs = resolve_workspace_configs()
        self.assertNotEqual(
            configs["librarian"].workspace_id,
            configs["researcher"].workspace_id,
        )


if __name__ == "__main__":
    unittest.main()
