import unittest

from hermes.personas.adapters import (
    DiscordMessage,
    route_discord_message,
    route_mcp_tool,
)


class PersonaAdapterTests(unittest.TestCase):
    def test_discord_requires_home_channel_and_allowlist(self) -> None:
        message = DiscordMessage(
            channel_id="chan-1",
            author_id="user-1",
            mentions=["assistant"],
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
            mentions=[],
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
            mentions=["tutor"],
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
            mentions=["tutor"],
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
            mentions=["assistant"],
            content="teach me distributed systems",
        )
        result = route_discord_message(
            message,
            home_channel_id="chan-1",
            allowed_users={"user-1"},
        )
        self.assertEqual(result.decision.value, "refuse_discord")
        self.assertEqual(result.hint_persona, "tutor")

    def test_mcp_route_has_typed_oos(self) -> None:
        result = route_mcp_tool("manage_tasks")
        self.assertEqual(result["ok"], False)
        self.assertEqual(result["errors"][0]["code"], "OUT_OF_SCOPE")
        self.assertEqual(result["errors"][0]["surface"], "mcp")


if __name__ == "__main__":
    unittest.main()
