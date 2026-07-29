"""Tests for the hermes-agent plugin adapter.

Scope: in-repo unit tests only. We do not import hermes-agent; instead
we feed the plugin fake ``MessageEvent``-shaped objects that satisfy
the structural Protocols declared in
:mod:`hermes.hermes_agent_plugin.dispatch`.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any, cast

from hermes.hermes_agent_plugin import dispatch as _dispatch_mod
from hermes.hermes_agent_plugin.dispatch import (
    HomeChannelConfig,
    _dispatch,
    register,
)

# Internal Protocols — the fake types below implement these structurally.
_MessageTypeLike = _dispatch_mod._MessageTypeLike
_SessionSourceLike = _dispatch_mod._SessionSourceLike
_PlatformLike = _dispatch_mod._PlatformLike

# ---------------------------------------------------------------------------
# Test doubles — minimal structural stand-ins for hermes-agent types
# ---------------------------------------------------------------------------


# Fakes typed as the same Protocols the plugin expects. mypy sees
# these as structural subtypes of MessageEventLike; runtime is plain
# dataclasses. cast at the call sites would also work but is
# uglier — the field annotations are the honest fix.


# Field types use the Protocols (not the nominal fake classes) so
# mypy sees FakeEvent as a structural subtype of MessageEventLike.
# The runtime is plain dataclasses.


@dataclass
class FakePlatform:
    value: str


@dataclass
class FakeMessageType:
    value: str


@dataclass
class FakeSource:
    platform: _PlatformLike
    chat_id: str | None
    chat_type: str | None
    user_id: str | None
    user_name: str | None = "tester"


@dataclass
class FakeEvent:
    text: str
    source: _SessionSourceLike
    message_type: _MessageTypeLike
    message_id: str | None = "m-1"
    internal: bool = False


class FakeAdapter:
    """Records ``send`` calls; raises if the plugin tries to do I/O."""

    def __init__(self, raise_on_send: bool = False) -> None:
        self.sent: list[dict[str, Any]] = []
        self.raise_on_send = raise_on_send

    async def send(self, *, chat_id: str, content: str) -> None:
        # Mirrors the real BasePlatformAdapter.send signature (async def,
        # chat_id + content keyword args). Plugin schedules this via
        # create_task; the test runner drives the loop via
        # _run_dispatch_collecting_tasks.
        if self.raise_on_send:
            raise RuntimeError("network down")
        self.sent.append({"chat_id": chat_id, "text": content})


@dataclass
class FakeGateway:
    adapters: dict[str, Any]


@dataclass
class FakeSessionStore:
    pass


@dataclass
class FakePluginContext:
    hooks: list[tuple[str, Any]]

    def register_hook(self, name: str, callback: Any) -> None:
        self.hooks.append((name, callback))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _discord_event(
    text: str,
    *,
    user_id: str = "user-1",
    chat_id: str = "chan-1",
    internal: bool = False,
    message_type: FakeMessageType | None = None,
) -> FakeEvent:
    # cast() at the construction sites: the fake dataclasses satisfy
    # the Protocols structurally, but mypy's nominal check on the
    # dataclass fields refuses the wider Protocol type. The runtime
    # values are unchanged.
    return FakeEvent(
        text=text,
        source=cast(_SessionSourceLike, FakeSource(
            platform=cast(_PlatformLike, FakePlatform("discord")),
            chat_id=chat_id,
            chat_type="group",
            user_id=user_id,
        )),
        message_type=cast(_MessageTypeLike, message_type or FakeMessageType("text")),
        internal=internal,
    )


_HOME = HomeChannelConfig(
    home_channel_id="chan-1",
    allowed_users=frozenset({"user-1"}),
)


def _action_of(result: dict[str, Any] | None) -> str | None:
    if result is None:
        return None
    return result.get("action")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Async test helpers
# ---------------------------------------------------------------------------


from collections.abc import Callable as _Callable


def _drive_dispatch(dispatch_callable: _Callable[[], object]) -> None:
    """Run a sync dispatch callable inside a fresh event loop and drain
    every task the dispatcher scheduled to completion.

    The dispatcher's hook callback is synchronous and uses
    ``asyncio.get_running_loop()`` to schedule refusal sends as
    fire-and-forget tasks. To exercise the side-channel synchronously:
      1. Start a fresh event loop.
      2. Call the dispatcher from inside that loop so its
         ``get_running_loop()`` returns our loop.
      3. Drain all pending tasks (sleep 0 cycles) until completion.
    """
    import asyncio as _a

    async def _driver() -> None:
        dispatch_callable()
        # Drain tasks the dispatcher scheduled. The dispatcher does no
        # awaits itself — only ``loop.create_task`` — so two yield points
        # is enough for the refusal-send coroutine to run.
        await _a.sleep(0)
        await _a.sleep(0)

    _a.run(_driver())

class PluginDispatchTests(unittest.TestCase):
    # ---- non-Discord / internal / non-text events: pass through ----

    def test_non_discord_event_passes_through(self) -> None:
        # cast() at the construction boundary: the fake dataclasses
        # are structural subtypes of the Protocols but mypy's nominal
        # dataclass check refuses the wider Protocol type.
        event = FakeEvent(
            text="hello",
            source=cast(_SessionSourceLike, FakeSource(
                platform=cast(_PlatformLike, FakePlatform("telegram")),
                chat_id="chan-1",
                chat_type="dm",
                user_id="user-1",
            )),
            message_type=cast(_MessageTypeLike, FakeMessageType("text")),
        )
        result = _dispatch(event, FakeGateway(adapters={}), FakeSessionStore(), home_channel=_HOME)
        self.assertIsNone(result)

    def test_internal_event_passes_through(self) -> None:
        event = _discord_event("system: handover", internal=True)
        result = _dispatch(event, FakeGateway(adapters={}), FakeSessionStore(), home_channel=_HOME)
        self.assertIsNone(result)

    def test_non_text_event_passes_through(self) -> None:
        event = _discord_event(
            "caption text",
            message_type=FakeMessageType("photo"),
        )
        result = _dispatch(event, FakeGateway(adapters={}), FakeSessionStore(), home_channel=_HOME)
        self.assertIsNone(result)

    # ---- Discord text event: gating rules ----

    def test_wrong_channel_is_ignored(self) -> None:
        event = _discord_event(
            "@assistant add task: buy coffee",
            chat_id="chan-OTHER",
        )
        result = _dispatch(event, FakeGateway(adapters={}), FakeSessionStore(), home_channel=_HOME)
        self.assertEqual(_action_of(result), "skip")

    def test_unauthorized_user_is_ignored(self) -> None:
        event = _discord_event(
            "@assistant add task: buy coffee",
            user_id="user-STRANGER",
        )
        result = _dispatch(event, FakeGateway(adapters={}), FakeSessionStore(), home_channel=_HOME)
        self.assertEqual(_action_of(result), "skip")

    def test_no_mention_is_ignored(self) -> None:
        event = _discord_event("hello everyone")
        result = _dispatch(event, FakeGateway(adapters={}), FakeSessionStore(), home_channel=_HOME)
        self.assertEqual(_action_of(result), "skip")

    def test_assistant_task_request_allows(self) -> None:
        """@assistant on a task request should pass through to the agent.

        The bot-name -> persona-id resolution layer is deployment-specific
        (lives in hermes-agent's adapter and the operator's .env). The
        plugin receives a list of already-resolved bot-identity strings
        in the message content; this test exercises the gate's allow
        path on that input, proving the core routing works once the
        VM-side mention extractor is in place.
        """
        event = _discord_event("@assistant add task: buy coffee")
        result = _dispatch(event, FakeGateway(adapters={}), FakeSessionStore(), home_channel=_HOME)
        self.assertEqual(result, {"action": "allow"})

    def test_tutor_tutoring_request_allows(self) -> None:
        """@tutor with conduct_tutoring-style content is allowed."""
        event = _discord_event("@tutor explain vector retrieval step by step")
        result = _dispatch(event, FakeGateway(adapters={}), FakeSessionStore(), home_channel=_HOME)
        self.assertEqual(result, {"action": "allow"})

    def test_tutor_task_request_refuses_with_assistant_hint(self) -> None:
        """@tutor asked to manage tasks -> REFUSE_DISCORD with @assistant hint.

        The classifier must strip the leading ``@persona`` token before
        matching intent regexes; otherwise the bare word "tutor" inside
        ``@tutor`` matches ``_TUTORING_INTENT`` and the gate wrongly
        ALLOWs a task-management request. This test pins the correct
        behavior.
        """
        adapter = FakeAdapter()
        gateway = FakeGateway(adapters={"discord": adapter})
        event = _discord_event("@tutor list tasks")

        def _do() -> None:
            result = _dispatch(event, gateway, FakeSessionStore(), home_channel=_HOME)
            self.assertEqual(_action_of(result), "skip")

        _drive_dispatch(_do)
        self.assertEqual(len(adapter.sent), 1)
        self.assertEqual(adapter.sent[0]["chat_id"], "chan-1")
        self.assertIn("@assistant", adapter.sent[0]["text"])

    def test_assistant_teach_request_refuses_with_tutor_hint(self) -> None:
        """@assistant asked to teach -> REFUSE_DISCORD with @tutor hint."""
        adapter = FakeAdapter()
        gateway = FakeGateway(adapters={"discord": adapter})
        event = _discord_event("@assistant teach me distributed systems")

        def _do() -> None:
            result = _dispatch(event, gateway, FakeSessionStore(), home_channel=_HOME)
            self.assertEqual(_action_of(result), "skip")

        _drive_dispatch(_do)
        self.assertEqual(len(adapter.sent), 1)
        self.assertIn("@tutor", adapter.sent[0]["text"])

    # ---- error / robustness paths ----

    def test_refusal_send_failure_does_not_raise(self) -> None:
        """A flaky Discord adapter must not crash the gateway.

        The dispatcher schedules the refusal send as a fire-and-forget
        task; the adapter raising inside that task must not propagate
        to the hook caller.
        """
        adapter = FakeAdapter(raise_on_send=True)
        gateway = FakeGateway(adapters={"discord": adapter})
        event = _discord_event("@tutor list tasks")

        def _do() -> None:
            result = _dispatch(event, gateway, FakeSessionStore(), home_channel=_HOME)
            self.assertEqual(_action_of(result), "skip")

        # Must not raise even though the dispatched task raises.
        _drive_dispatch(_do)
        self.assertEqual(adapter.sent, [])

    def test_missing_discord_adapter_does_not_raise(self) -> None:
        """Gateway with no discord adapter must not crash on a refused action."""
        gateway = FakeGateway(adapters={})
        event = _discord_event("@tutor list tasks")
        result = _dispatch(event, gateway, FakeSessionStore(), home_channel=_HOME)
        self.assertEqual(_action_of(result), "skip")

    def test_confirm_delete_is_skipped_pending_interaction(self) -> None:
        """Ticket 74 handles the actual button flow. The plugin signals skip."""
        event = _discord_event("@assistant delete my tasks")
        result = _dispatch(event, FakeGateway(adapters={}), FakeSessionStore(), home_channel=_HOME)
        assert result is not None  # narrow for type-checker
        self.assertEqual(_action_of(result), "skip")
        self.assertIn("confirm_delete", result["reason"])


class PluginRegisterTests(unittest.TestCase):
    def test_register_registers_pre_gateway_dispatch_hook(self) -> None:
        """The standard entry point hooks pre_gateway_dispatch exactly once."""
        ctx = FakePluginContext(hooks=[])
        register(ctx, home_channel=_HOME)
        self.assertEqual(len(ctx.hooks), 1)
        name, callback = ctx.hooks[0]
        self.assertEqual(name, "pre_gateway_dispatch")
        self.assertTrue(callable(callback))

    def test_registered_callback_routes_through_dispatch(self) -> None:
        """Sanity: the registered callback invokes the same logic as _dispatch."""
        ctx = FakePluginContext(hooks=[])
        register(ctx, home_channel=_HOME)
        _, callback = ctx.hooks[0]
        event = _discord_event("@assistant add task: buy coffee")
        result = callback(event, FakeGateway(adapters={}), FakeSessionStore())
        self.assertEqual(result, {"action": "allow"})

    def test_registered_callback_ignores_extra_kwargs(self) -> None:
        """hermes-agent may pass additional kwargs the plugin does not need."""
        ctx = FakePluginContext(hooks=[])
        register(ctx, home_channel=_HOME)
        _, callback = ctx.hooks[0]
        event = _discord_event("@assistant add task: buy coffee")
        result = callback(
            event,
            FakeGateway(adapters={}),
            FakeSessionStore(),
            something_else="ignored",
        )
        self.assertEqual(result, {"action": "allow"})


if __name__ == "__main__":
    unittest.main()
