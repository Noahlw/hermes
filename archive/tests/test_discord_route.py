"""Discord routing contract tests — policy layer (hermes.personas, stable API).

The gateway adapter (hermes_agent.discord_adapter) is a thin executor behind
route_discord_message(); these tests pin the routing decision surface the
adapter relies on. Network-free: no discord client is constructed.
"""

from __future__ import annotations

from hermes.personas.adapters import DiscordMessage, route_discord_message
from hermes.personas.contract_gate import Decision

HOME_CHANNEL = "100"
ALLOWED = {"555"}


def _msg(
    channel_id: str = HOME_CHANNEL,
    author_id: str = "555",
    mentions: list[str] | None = None,
    content: str = "hello",
    confirm_delete: bool = False,
) -> DiscordMessage:
    return DiscordMessage(
        channel_id=channel_id,
        author_id=author_id,
        mentions=["assistant"] if mentions is None else mentions,
        content=content,
        confirm_delete=confirm_delete,
    )


def test_home_channel_allowlisted_mention_routes_to_persona() -> None:
    route = route_discord_message(_msg(), HOME_CHANNEL, ALLOWED)
    assert not route.ignored
    assert route.persona_id == "assistant"
    assert route.decision is Decision.ALLOW
    assert route.confirm_required is False


def test_non_home_channel_ignored() -> None:
    route = route_discord_message(_msg(channel_id="999"), HOME_CHANNEL, ALLOWED)
    assert route.ignored is True


def test_non_allowlisted_author_ignored() -> None:
    route = route_discord_message(_msg(author_id="777"), HOME_CHANNEL, ALLOWED)
    assert route.ignored is True


def test_no_mention_ignored() -> None:
    route = route_discord_message(_msg(mentions=[]), HOME_CHANNEL, ALLOWED)
    assert route.ignored is True


def test_mention_tutor_routes_to_tutor() -> None:
    route = route_discord_message(
        _msg(mentions=["tutor"], content="what is 2+2?"), HOME_CHANNEL, ALLOWED
    )
    assert not route.ignored
    assert route.persona_id == "tutor"
    # tutor contract allows conduct_tutoring (its identity default)
    assert route.decision is Decision.ALLOW


def test_tutor_asked_to_manage_tasks_refuses_with_hint() -> None:
    route = route_discord_message(
        _msg(mentions=["tutor"], content="add a task to my todos"), HOME_CHANNEL, ALLOWED
    )
    assert not route.ignored
    assert route.decision is Decision.REFUSE_DISCORD
    # tutor has no manage_tasks; the gate suggests a persona that does.
    assert route.hint_persona in {"assistant", "main_agent"}


def test_delete_without_confirm_refuses_with_confirm_required() -> None:
    route = route_discord_message(
        _msg(content="delete my tasks"), HOME_CHANNEL, ALLOWED
    )
    assert not route.ignored
    assert route.decision is Decision.REFUSE_DISCORD
    assert route.confirm_required is True
    assert "confirm" in route.reason.lower()


def test_delete_with_confirm_allowed() -> None:
    route = route_discord_message(
        _msg(content="delete my tasks", confirm_delete=True), HOME_CHANNEL, ALLOWED
    )
    assert not route.ignored
    assert route.confirm_required is False
