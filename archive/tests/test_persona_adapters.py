import unittest

from hermes.personas.adapters import (
    DiscordMessage,
    route_discord_message,
    route_mcp_tool,
)
from hermes.personas.contract_gate import Decision


class PersonaAdapterTests(unittest.TestCase):
    def test_discord_requires_home_channel_and_allowlist(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("assistant",),
            content="add task: buy coffee",
        )
        ignored_channel = route_discord_message(
            message,
            home_channel_id="chan-2",
            allowed_users={"user-1"},
        )
        ignored_user = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-2"},
        )

        self.assertTrue(ignored_channel.ignored)
        self.assertTrue(ignored_user.ignored)

    def test_discord_ignores_without_mention(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=(),
            content="hello everyone",
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertTrue(result.ignored)

    def test_discord_maps_mention_to_persona(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("tutor",),
            content="teach me retrieval indexing",
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertFalse(result.ignored)
        self.assertEqual(result.persona_id, "tutor")

    def test_tutor_defaults_to_tutoring_by_mention(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("tutor",),
            content="explain vector retrieval step by step",
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision.value, "allow")

    def test_refuse_result_preserves_hint_persona(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("assistant",),
            content="teach me distributed systems",
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision.value, "refuse_discord")
        self.assertEqual(result.hint_persona, "tutor")

    def test_tutor_allows_prompts_that_mention_task_topic(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("tutor",),
            content="explain task decomposition in LangGraph step by step",
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision.value, "allow")
        self.assertIsNone(result.hint_persona)

    def test_tutor_refuses_explicit_task_management(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("tutor",),
            content="list tasks",
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision.value, "refuse_discord")
        self.assertEqual(result.hint_persona, "assistant")

    def test_tutor_refuses_list_my_tasks_phrasing(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("tutor",),
            content="list my tasks",
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision.value, "refuse_discord")
        self.assertEqual(result.hint_persona, "assistant")

    def test_tutor_refuses_todo_management_phrasing(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("tutor",),
            content="list todos",
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision.value, "refuse_discord")
        self.assertEqual(result.hint_persona, "assistant")

    def test_assistant_teach_about_todos_refuses_with_tutor_hint(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("assistant",),
            content="teach me about todos",
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision.value, "refuse_discord")
        self.assertEqual(result.hint_persona, "tutor")

    def test_assistant_teach_about_tasks_refuses_with_tutor_hint(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("assistant",),
            content="teach me about task queues",
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision.value, "refuse_discord")
        self.assertEqual(result.hint_persona, "tutor")

    def test_assistant_still_routes_explicit_task_management(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("assistant",),
            content="add task: buy coffee",
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision.value, "allow")

    def test_mcp_route_has_typed_oos(self) -> None:
        result = route_mcp_tool("manage_tasks")
        self.assertEqual(result["ok"], False)
        self.assertEqual(result["errors"][0]["code"], "OUT_OF_SCOPE")
        self.assertEqual(result["errors"][0]["surface"], "mcp")

    # --- New tests ---

    def test_mcp_job_persona_librarian(self) -> None:
        result = route_mcp_tool("library_search")
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["job_persona"], "librarian")

    def test_mcp_job_persona_researcher(self) -> None:
        result = route_mcp_tool("conduct_research")
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["job_persona"], "researcher")

    def test_mcp_job_persona_absent_on_oos(self) -> None:
        result = route_mcp_tool("manage_tasks")
        self.assertNotIn("job_persona", result)

    def test_mcp_job_persona_librarian_uppercase(self) -> None:
        result = route_mcp_tool("LIBRARY_SEARCH")
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["job_persona"], "librarian")

    def test_mcp_job_persona_researcher_mixed_case(self) -> None:
        result = route_mcp_tool("Conduct_Research")
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["job_persona"], "researcher")

    def test_mcp_job_persona_librarian_with_whitespace(self) -> None:
        result = route_mcp_tool("  library_search  ")
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["job_persona"], "librarian")

    def test_confirm_delete_refuses_without_flag(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("assistant",),
            content="delete my tasks",
            confirm_delete=False,
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision, Decision.REFUSE_DISCORD)
        self.assertTrue(result.confirm_required)

    def test_confirm_delete_allows_with_flag(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("assistant",),
            content="delete my tasks",
            confirm_delete=True,
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision, Decision.ALLOW)

    def test_confirm_delete_refuses_delete_all_tasks(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("assistant",),
            content="delete all tasks",
            confirm_delete=False,
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision, Decision.REFUSE_DISCORD)
        self.assertTrue(result.confirm_required)

    def test_confirm_delete_refuses_delete_this_task(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("assistant",),
            content="delete this task",
            confirm_delete=False,
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision, Decision.REFUSE_DISCORD)
        self.assertTrue(result.confirm_required)

    def test_confirm_delete_refuses_delete_completed_tasks(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("assistant",),
            content="delete completed tasks",
            confirm_delete=False,
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision, Decision.REFUSE_DISCORD)
        self.assertTrue(result.confirm_required)

    def test_confirm_delete_refuses_wipe_my_todos(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("assistant",),
            content="wipe my todos",
            confirm_delete=False,
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision, Decision.REFUSE_DISCORD)
        self.assertTrue(result.confirm_required)

    def test_confirm_delete_ignored_when_no_delete_intent(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("assistant",),
            content="add task: buy coffee",
            confirm_delete=False,
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision, Decision.ALLOW)
        self.assertFalse(result.confirm_required)

    def test_confirm_delete_tutor_delete_request(self) -> None:
        # Tutor doesn't have manage_tasks, so the gate refusal takes
        # precedence over confirm_delete — confirm_required should not
        # be set because the action itself is not allowed.
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=("tutor",),
            content="delete my tasks",
            confirm_delete=False,
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision, Decision.REFUSE_DISCORD)
        self.assertFalse(result.confirm_required)

    def test_discord_message_mentions_is_tuple(self) -> None:
        msg = DiscordMessage(
            channel_id="c", author_id="u", mentions=("a",), content="hello"
        )
        self.assertIsInstance(msg.mentions, tuple)


if __name__ == "__main__":
    unittest.main()
