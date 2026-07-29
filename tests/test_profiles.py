"""Tests for profile config templates and provisioning plan."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from hermes.profiles.config import (
    PROFILE_DEFINITIONS,
    ProfileDefinition,
    ProfileKind,
    generate_config_yaml,
    generate_cron_jobs_json,
    generate_env_file,
    generate_honcho_json,
)
from hermes.profiles.provision import plan_provision


class ProfileDefinitionTests(unittest.TestCase):
    """Tests for the ProfileDefinition data class."""

    def test_all_five_personas_are_defined(self) -> None:
        self.assertEqual(
            frozenset(PROFILE_DEFINITIONS),
            frozenset({"main_agent", "assistant", "tutor", "librarian", "researcher"}),
        )

    def test_discord_personas_have_bot_tokens(self) -> None:
        discord_ids = {"main_agent", "assistant", "tutor"}
        for pid in discord_ids:
            profile = PROFILE_DEFINITIONS[pid]
            self.assertEqual(profile.kind, ProfileKind.DISCORD)
            self.assertTrue(profile.enable_discord)
            self.assertTrue(
                profile.discord_bot_token_env,
                f"{pid} missing discord_bot_token_env",
            )
            self.assertIsNotNone(profile.home_channel)

    def test_mcp_personas_do_not_enable_discord(self) -> None:
        mcp_ids = {"librarian", "researcher"}
        for pid in mcp_ids:
            profile = PROFILE_DEFINITIONS[pid]
            self.assertEqual(profile.kind, ProfileKind.MCP)
            self.assertFalse(profile.enable_discord)
            self.assertEqual(profile.discord_bot_token_env, "")

    def test_declaring_discord_profile_without_token_raises(self) -> None:
        with self.assertRaises(ValueError):
            ProfileDefinition(
                persona_id="test",
                kind=ProfileKind.DISCORD,
                enable_discord=True,
                home_channel="chan",
                discord_bot_token_env="",
            )

    def test_declaring_discord_profile_without_enable_discord_raises(self) -> None:
        with self.assertRaises(ValueError):
            ProfileDefinition(
                persona_id="test",
                kind=ProfileKind.DISCORD,
                enable_discord=False,
                home_channel="chan",
                discord_bot_token_env="TOKEN",
            )

    def test_declaring_mcp_profile_with_discord_raises(self) -> None:
        with self.assertRaises(ValueError):
            ProfileDefinition(
                persona_id="test",
                kind=ProfileKind.MCP,
                enable_discord=True,
                home_channel="chan",
                discord_bot_token_env="TOKEN",
            )

    def test_only_main_agent_has_cron_enabled(self) -> None:
        for pid, profile in PROFILE_DEFINITIONS.items():
            if pid == "main_agent":
                self.assertTrue(profile.enable_cron, f"{pid} should have cron")
            else:
                self.assertFalse(profile.enable_cron, f"{pid} should not have cron")

    def test_all_discord_personas_share_home_channel(self) -> None:
        channel_refs = {
            profile.home_channel
            for profile in PROFILE_DEFINITIONS.values()
            if profile.kind == ProfileKind.DISCORD
        }
        # All three reference the same env-var placeholder.
        self.assertEqual(channel_refs, {"DISCORD_HOME_CHANNEL"})


class ConfigGenerationTests(unittest.TestCase):
    """Tests for the config.yaml, .env, honcho.json, and cron/jobs.json generators."""

    def test_config_yaml_includes_multiplex(self) -> None:
        for pid, profile in PROFILE_DEFINITIONS.items():
            yaml_text = generate_config_yaml(profile)
            self.assertIn("multiplex_profiles: true", yaml_text)
            self.assertIn(pid, yaml_text)

    def test_discord_config_yaml_includes_adapter_block(self) -> None:
        for pid in ("main_agent", "assistant", "tutor"):
            profile = PROFILE_DEFINITIONS[pid]
            yaml_text = generate_config_yaml(profile)
            self.assertIn("adapters:", yaml_text)
            self.assertIn("discord:", yaml_text)
            self.assertIn("required_mention: true", yaml_text)

    def test_mcp_config_yaml_has_no_adapter_block(self) -> None:
        for pid in ("librarian", "researcher"):
            profile = PROFILE_DEFINITIONS[pid]
            yaml_text = generate_config_yaml(profile)
            self.assertNotIn("adapters:", yaml_text)

    def test_main_agent_config_yaml_has_cron_block(self) -> None:
        profile = PROFILE_DEFINITIONS["main_agent"]
        yaml_text = generate_config_yaml(profile)
        self.assertIn("cron:", yaml_text)
        self.assertIn("enabled: true", yaml_text)

    def test_non_main_agent_config_yaml_has_no_cron_block(self) -> None:
        for pid in ("assistant", "tutor", "librarian", "researcher"):
            profile = PROFILE_DEFINITIONS[pid]
            yaml_text = generate_config_yaml(profile)
            self.assertNotIn("cron:", yaml_text)

    def test_env_file_discord_has_token_placeholder(self) -> None:
        profile = PROFILE_DEFINITIONS["assistant"]
        env_text = generate_env_file(profile)
        self.assertIn("DISCORD_BOT_TOKEN_ASSISTANT", env_text)
        self.assertIn("PLACEHOLDER", env_text)
        self.assertIn("DISCORD_ALLOWED_USERS", env_text)

    def test_env_file_mcp_has_no_discord(self) -> None:
        profile = PROFILE_DEFINITIONS["librarian"]
        env_text = generate_env_file(profile)
        self.assertNotIn("DISCORD_BOT_TOKEN", env_text)
        self.assertNotIn("DISCORD_ALLOWED_USERS", env_text)

    def test_honcho_json_has_distinct_peer_and_workspace(self) -> None:
        seen_peers: set[str] = set()
        seen_workspaces: set[str] = set()
        for pid, profile in PROFILE_DEFINITIONS.items():
            honcho = json.loads(generate_honcho_json(profile))
            expected = f"hermes_{pid}"
            self.assertEqual(honcho["ai_peer"], expected)
            self.assertEqual(honcho["workspace_id"], expected)
            seen_peers.add(honcho["ai_peer"])
            seen_workspaces.add(honcho["workspace_id"])
        # All five are distinct.
        self.assertEqual(len(seen_peers), 5)
        self.assertEqual(len(seen_workspaces), 5)

    def test_honcho_json_is_valid_json(self) -> None:
        for profile in PROFILE_DEFINITIONS.values():
            parsed = json.loads(generate_honcho_json(profile))
            self.assertIn("ai_peer", parsed)
            self.assertIn("workspace_id", parsed)

    def test_cron_jobs_json_main_agent_has_ops_digest(self) -> None:
        profile = PROFILE_DEFINITIONS["main_agent"]
        cron = json.loads(generate_cron_jobs_json(profile))
        self.assertEqual(len(cron["jobs"]), 1)
        self.assertEqual(cron["jobs"][0]["id"], "ops-digest")
        self.assertEqual(cron["jobs"][0]["schedule"], "0 7 * * *")

    def test_cron_jobs_json_non_main_agent_is_empty(self) -> None:
        for pid in ("assistant", "tutor", "librarian", "researcher"):
            profile = PROFILE_DEFINITIONS[pid]
            cron = json.loads(generate_cron_jobs_json(profile))
            self.assertEqual(cron["jobs"], [])

    def test_main_agent_ops_digest_schedule_is_one_hour_after_vm_health_check(self) -> None:
        """The spec requires 0 7 * * * (one hour after vm-health-check at 0 6 * * *)."""
        profile = PROFILE_DEFINITIONS["main_agent"]
        cron = json.loads(generate_cron_jobs_json(profile))
        ops_digest = cron["jobs"][0]
        self.assertEqual(ops_digest["schedule"], "0 7 * * *")


class ProvisionPlanTests(unittest.TestCase):
    """Tests for the provisioning plan builder."""

    def test_full_plan_has_five_profiles(self) -> None:
        plan = plan_provision()
        self.assertEqual(len(plan.profiles), 5)
        for pid in ("main_agent", "assistant", "tutor", "librarian", "researcher"):
            self.assertIn(pid, plan.profiles)

    def test_partial_plan_filters_persona_ids(self) -> None:
        plan = plan_provision(persona_ids=frozenset({"assistant", "librarian"}))
        self.assertEqual(len(plan.profiles), 2)
        self.assertIn("assistant", plan.profiles)
        self.assertIn("librarian", plan.profiles)
        self.assertNotIn("main_agent", plan.profiles)
        self.assertNotIn("tutor", plan.profiles)
        self.assertNotIn("researcher", plan.profiles)

    def test_unknown_persona_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            plan_provision(persona_ids=frozenset({"developer"}))

    def test_plan_dirs_are_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = plan_provision(root=tmp)
            for d in plan.dirs:
                self.assertTrue(
                    d.startswith(tmp),
                    f"Directory '{d}' not under root '{tmp}'",
                )

    def test_plan_files_are_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = plan_provision(root=tmp)
            for rel_path, _content in plan.files:
                full = os.path.join(tmp, rel_path)
                self.assertTrue(
                    full.startswith(tmp),
                    f"File '{full}' not under root '{tmp}'",
                )

    def test_plan_has_expected_files_per_profile(self) -> None:
        plan = plan_provision()
        # 5 profiles × 4 files each = 20 files
        self.assertEqual(plan.file_count, 20)
        expected_files = {"config.yaml", ".env", "honcho.json", "cron/jobs.json"}
        for rel_path, _content in plan.files:
            basename = Path(rel_path).name
            if basename == "jobs.json":
                # cron/jobs.json → basename is jobs.json
                self.assertIn("jobs.json", rel_path)
            else:
                self.assertIn(basename, expected_files)

    def test_plan_validate_succeeds_on_valid_plan(self) -> None:
        plan = plan_provision()
        errors = plan.validate()
        self.assertEqual(errors, [])

    def test_plan_validate_detects_mismatched_key(self) -> None:
        """Manually construct a plan with a mismatched key."""
        from hermes.profiles.provision import ProvisionPlan
        from hermes.profiles.config import PROFILE_DEFINITIONS

        bad_profiles = {"main_agent": PROFILE_DEFINITIONS["assistant"]}
        plan = ProvisionPlan(
            root="/tmp/test",
            profiles=bad_profiles,
            dirs=(),
            files=(),
        )
        errors = plan.validate()
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("does not match" in e for e in errors))

    def test_plan_standard_root_is_user_home(self) -> None:
        plan = plan_provision()
        self.assertTrue(plan.root.startswith(os.path.expanduser("~")))

    def test_plan_custom_root(self) -> None:
        plan = plan_provision(root="/opt/hermes/profiles")
        self.assertEqual(plan.root, "/opt/hermes/profiles")

    def test_plan_each_profile_has_profile_home_dir(self) -> None:
        plan = plan_provision(root="/tmp/p")
        for pid in plan.profiles:
            home = os.path.join("/tmp/p", pid)
            self.assertIn(home, plan.dirs, f"Missing home dir for {pid}")

    def test_plan_each_profile_has_subdirs(self) -> None:
        plan = plan_provision(root="/tmp/p")
        for pid in plan.profiles:
            home = os.path.join("/tmp/p", pid)
            for sub in ("memory", "sessions", "skills"):
                self.assertIn(os.path.join(home, sub), plan.dirs)

    def test_config_content_is_not_empty(self) -> None:
        plan = plan_provision()
        for rel_path, content in plan.files:
            self.assertTrue(
                content.strip(),
                f"File '{rel_path}' has empty content",
            )

    # --- Behavioral rules from #71 acceptance ---

    def test_all_three_discord_profiles_route_to_same_home_channel(self) -> None:
        """Acceptance: all profiles route to the same DISCORD_HOME_CHANNEL."""
        plan = plan_provision()
        for pid in ("main_agent", "assistant", "tutor"):
            profile = plan.profiles[pid]
            self.assertEqual(profile.home_channel, "DISCORD_HOME_CHANNEL")

    def test_discord_tokens_are_distinct_across_profiles(self) -> None:
        """Acceptance: each bot has its own token env var."""
        tokens = {
            PROFILE_DEFINITIONS[pid].discord_bot_token_env
            for pid in ("main_agent", "assistant", "tutor")
        }
        self.assertEqual(len(tokens), 3)

    def test_env_file_no_hardcoded_real_token(self) -> None:
        """Acceptance: .env files use placeholders, not real tokens."""
        for profile in PROFILE_DEFINITIONS.values():
            env_text = generate_env_file(profile)
            # No env file should contain a plausible real token (≥40 alphanumeric chars
            # that isn't PLACEHOLDER).
            import re
            # Look for anything that looks like a base64/stripped Discord token
            # (long alphanumeric string).  The placeholder itself contains the word
            # PLACEHOLDER so it won't match.
            suspicious = re.findall(r'"[A-Za-z0-9_-]{40,}"', env_text)
            self.assertEqual(
                suspicious, [],
                f"{profile.persona_id} .env contains potential real token: {suspicious}",
            )


if __name__ == "__main__":
    unittest.main()
