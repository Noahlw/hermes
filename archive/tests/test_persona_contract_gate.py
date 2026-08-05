import unittest

from hermes.personas.contract_gate import (
    V1_OOS_ACTIONS,
    Decision,
    _validate_contracts,
    decide_discord_action,
    decide_mcp_tool,
    load_contracts,
)


class PersonaContractGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Verify contracts load without error before running tests.
        cls.contracts = load_contracts()

    def test_contracts_load_all_five_personas(self) -> None:
        self.assertIn("assistant", self.contracts.all_personas)
        self.assertIn("tutor", self.contracts.all_personas)
        self.assertIn("main_agent", self.contracts.all_personas)
        self.assertIn("librarian", self.contracts.all_personas)
        self.assertIn("researcher", self.contracts.all_personas)

    def test_discord_personas_are_the_three_bot_personas(self) -> None:
        self.assertEqual(
            self.contracts.discord_personas,
            frozenset({"assistant", "tutor", "main_agent"}),
        )

    def test_developer_is_not_in_contracts(self) -> None:
        self.assertNotIn("developer", self.contracts.all_personas)

    def test_v1_oos_actions_are_immutable(self) -> None:
        with self.assertRaises(AttributeError):
            V1_OOS_ACTIONS.add("manage_tasks")  # type: ignore[attr-defined]

    def test_all_personas_are_immutable(self) -> None:
        with self.assertRaises(AttributeError):
            self.contracts.all_personas.add("new_persona")  # type: ignore[attr-defined]

    def test_assistant_allows_tasks_and_rejects_tutoring(self) -> None:
        allowed = decide_discord_action("assistant", "manage_tasks")
        rejected = decide_discord_action("assistant", "conduct_tutoring")

        self.assertEqual(allowed.decision, Decision.ALLOW)
        self.assertEqual(rejected.decision, Decision.REFUSE_DISCORD)
        self.assertEqual(rejected.hint_persona, "tutor")

    def test_tutor_allows_tutoring_and_rejects_tasks(self) -> None:
        allowed = decide_discord_action("tutor", "conduct_tutoring")
        rejected = decide_discord_action("tutor", "manage_tasks")

        self.assertEqual(allowed.decision, Decision.ALLOW)
        self.assertEqual(rejected.decision, Decision.REFUSE_DISCORD)
        self.assertEqual(rejected.hint_persona, "assistant")

    def test_main_agent_is_discord_superset(self) -> None:
        self.assertEqual(
            decide_discord_action("main_agent", "manage_tasks").decision,
            Decision.ALLOW,
        )
        self.assertEqual(
            decide_discord_action("main_agent", "conduct_tutoring").decision,
            Decision.ALLOW,
        )
        self.assertEqual(
            decide_discord_action("main_agent", "run_ops_digest").decision,
            Decision.ALLOW,
        )
        self.assertEqual(
            decide_discord_action("main_agent", "compose_digest").decision,
            Decision.ALLOW,
        )

    def test_developer_is_unknown_persona(self) -> None:
        result = decide_discord_action("developer", "generate_plan")
        self.assertEqual(result.decision, Decision.REFUSE_DISCORD)

    def test_plan_execute_is_v1_oos(self) -> None:
        self.assertEqual(
            decide_discord_action("main_agent", "execute_plan").decision,
            Decision.REFUSE_DISCORD,
        )

    def test_mcp_tools_are_librarian_or_researcher_only(self) -> None:
        self.assertEqual(
            decide_mcp_tool("library_search").decision,
            Decision.ALLOW,
        )
        self.assertEqual(
            decide_mcp_tool("conduct_research").decision,
            Decision.ALLOW,
        )
        self.assertEqual(
            decide_mcp_tool("manage_tasks").decision,
            Decision.MCP_OOS,
        )
        self.assertEqual(
            decide_mcp_tool("conduct_tutoring").decision,
            Decision.MCP_OOS,
        )

    def test_systemic_flag_is_set_for_repeat_mcp_misuse(self) -> None:
        result = decide_mcp_tool("manage_tasks", misuse_count=3)
        self.assertEqual(result.decision, Decision.MCP_OOS)
        self.assertTrue(result.systemic_escalation)

    def test_assistant_unknown_action_gets_hint(self) -> None:
        result = decide_discord_action("assistant", "run_ops_digest")
        self.assertEqual(result.decision, Decision.REFUSE_DISCORD)
        self.assertEqual(result.hint_persona, "main_agent")

    def test_tutor_unknown_action_gets_hint(self) -> None:
        result = decide_discord_action("tutor", "compose_digest")
        self.assertEqual(result.decision, Decision.REFUSE_DISCORD)
        self.assertIsNotNone(result.hint_persona)

    def test_non_discord_persona_is_refused(self) -> None:
        result = decide_discord_action("librarian", "library_search")
        self.assertEqual(result.decision, Decision.REFUSE_DISCORD)

    # --- Validation tests ---

    def test_validate_rejects_duplicate_persona_id(self) -> None:
        with self.assertRaises(ValueError):
            _validate_contracts([
                {"persona_id": "dup", "purpose": "x", "allowed_actions": ["a"]},
                {"persona_id": "dup", "purpose": "y", "allowed_actions": ["b"]},
            ])

    def test_validate_rejects_missing_persona_id(self) -> None:
        with self.assertRaises(ValueError):
            _validate_contracts([{"purpose": "x", "allowed_actions": ["a"]}])

    def test_validate_rejects_missing_purpose(self) -> None:
        with self.assertRaises(ValueError):
            _validate_contracts([{"persona_id": "x", "allowed_actions": ["a"]}])

    def test_validate_rejects_no_actions_or_jobs(self) -> None:
        with self.assertRaises(ValueError):
            _validate_contracts([{"persona_id": "x", "purpose": "test"}])

    def test_validate_rejects_non_list_allowed_actions(self) -> None:
        with self.assertRaises(ValueError):
            _validate_contracts([
                {"persona_id": "x", "purpose": "test", "allowed_actions": "not_a_list"},
            ])

    def test_validate_rejects_non_string_action_item(self) -> None:
        with self.assertRaises(TypeError):
            _validate_contracts([
                {"persona_id": "main_agent", "purpose": "test", "allowed_actions": [123]},
            ])

    def test_validate_rejects_non_list_allowed_jobs(self) -> None:
        with self.assertRaises(ValueError):
            _validate_contracts([
                {"persona_id": "x", "purpose": "test", "allowed_jobs": None},
            ])

    def test_validate_rejects_non_string_job_item(self) -> None:
        with self.assertRaises(TypeError):
            _validate_contracts([
                {"persona_id": "librarian", "purpose": "test", "allowed_jobs": [True]},
            ])

    # --- MCP case normalization ---

    def test_mcp_case_normalization_allows_uppercase(self) -> None:
        self.assertEqual(
            decide_mcp_tool("LIBRARY_SEARCH").decision,
            Decision.ALLOW,
        )

    def test_mcp_case_normalization_allows_mixed_case(self) -> None:
        self.assertEqual(
            decide_mcp_tool("Conduct_Research").decision,
            Decision.ALLOW,
        )

    def test_mcp_case_normalization_oos_still_works(self) -> None:
        self.assertEqual(
            decide_mcp_tool("MANAGE_TASKS").decision,
            Decision.MCP_OOS,
        )

    # --- Roster allowlist ---

    def test_validate_rejects_unknown_persona_id(self) -> None:
        with self.assertRaises(ValueError):
            _validate_contracts([
                {"persona_id": "developer", "purpose": "old draft", "allowed_actions": ["a"]},
            ])

    def test_validate_rejects_user_created_persona(self) -> None:
        with self.assertRaises(ValueError):
            _validate_contracts([
                {"persona_id": "custom_helper", "purpose": "x", "allowed_actions": ["a"]},
            ])

    def test_validate_rejects_discord_persona_without_actions(self) -> None:
        with self.assertRaises(ValueError):
            _validate_contracts([
                {"persona_id": "assistant", "purpose": "test", "allowed_jobs": ["library_search"]},
            ])

    def test_validate_rejects_job_backed_with_actions(self) -> None:
        with self.assertRaises(ValueError):
            _validate_contracts([
                {"persona_id": "librarian", "purpose": "test", "allowed_actions": ["a"]},
            ])

    def test_validate_rejects_empty_actions(self) -> None:
        with self.assertRaises(ValueError):
            _validate_contracts([
                {"persona_id": "main_agent", "purpose": "test", "allowed_actions": []},
            ])

    # --- Deep-frozen mappings ---

    def test_contract_data_persona_actions_is_read_only(self) -> None:
        with self.assertRaises(TypeError):
            self.contracts.persona_actions["assistant"] = frozenset()  # type: ignore[index]

    def test_contract_data_persona_jobs_is_read_only(self) -> None:
        with self.assertRaises(TypeError):
            self.contracts.persona_jobs["librarian"] = frozenset()  # type: ignore[index]

    # --- Tie-break pinning ---

    def test_specialist_tie_break_prefers_assistant_over_tutor(self) -> None:
        # Both assistant and tutor have library_search. _suggest_persona
        # must deterministically return "assistant" because the fixed
        # specialist priority puts assistant before tutor.
        from hermes.personas.contract_gate import _suggest_persona
        self.assertEqual(
            _suggest_persona("library_search", self.contracts),
            "assistant",
        )


if __name__ == "__main__":
    unittest.main()
