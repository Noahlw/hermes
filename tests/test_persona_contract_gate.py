import unittest

from hermes.personas.contract_gate import (
    Decision,
    decide_discord_action,
    decide_mcp_tool,
)


class PersonaContractGateTests(unittest.TestCase):
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

    def test_developer_and_plan_execute_are_v1_oos(self) -> None:
        self.assertEqual(
            decide_discord_action("developer", "generate_plan").decision,
            Decision.REFUSE_DISCORD,
        )
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


if __name__ == "__main__":
    unittest.main()
