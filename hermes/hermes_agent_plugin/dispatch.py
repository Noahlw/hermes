"""pre_gateway_dispatch hook implementation that wraps the persona gate.

Module structure
----------------
- :func:`register` — the standard hermes-agent plugin entry point. Drops the
  hook and never modifies global state. Safe to call at hermes-agent
  startup.
- :func:`_dispatch` — the hook callback. Maps a hermes-agent
  :class:`MessageEvent` to this repo's :class:`DiscordMessage`, runs the
  contract gate via :func:`route_discord_message`, and returns the action
  dict that the gateway expects.

Why a Protocol (and not an import) for the hermes-agent types
------------------------------------------------------------
This package must remain importable in a checkout that does not
vendor hermes-agent. We declare a structural Protocol for the
relevant pieces of ``MessageEvent`` / ``SessionSource`` /
``MessageType`` / ``Platform`` so the conversion logic is type-checked
in this repo and tested with fakes; the real hermes-agent types
satisfy these Protocols by structural compatibility (verified at
``docs/adr/0004-hermes-agent-integration-model.md``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from hermes.personas.adapters import (
    Decision,
    DiscordMessage,
    DiscordRoute,
    route_discord_message,
)

# ---------------------------------------------------------------------------
# Structural Protocols for hermes-agent types
# ---------------------------------------------------------------------------


class _PlatformLike(Protocol):
    """Subset of ``gateway.config.Platform`` we actually read."""

    value: str


class _SessionSourceLike(Protocol):
    """Subset of ``gateway.session.SessionSource`` fields this plugin reads."""

    platform: _PlatformLike | str
    chat_id: str | None
    chat_type: str | None
    user_id: str | None
    user_name: str | None


class _MessageTypeLike(Protocol):
    """Subset of ``gateway.platforms.base.MessageType`` values we read."""

    value: str


class MessageEventLike(Protocol):
    """Subset of ``gateway.platforms.base.MessageEvent`` fields this plugin reads.

    Verified against ``NousResearch/hermes-agent`` commit ``d71033a``.
    """

    text: str
    source: _SessionSourceLike
    message_type: _MessageTypeLike
    message_id: str | None
    internal: bool


class GatewayLike(Protocol):
    """Subset of ``gateway.run.GatewayRunner`` that the plugin may call.

    The plugin only invokes ``adapters[platform].send(...)`` to deliver
    the bot's refusal message; it does not touch the agent loop, the
    session store, or any other gateway state.
    """

    adapters: dict[str, Any]


class SessionStoreLike(Protocol):
    """Empty protocol — the gate does not currently need session writes."""


class PluginContextLike(Protocol):
    """Subset of ``hermes_cli.plugins.PluginContext`` we call."""

    def register_hook(self, name: str, callback: Callable[..., Any]) -> None: ...


# ---------------------------------------------------------------------------
# Channel / allowlist resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HomeChannelConfig:
    """Operator-provided values that live outside hermes-agent's own config."""

    home_channel_id: str
    allowed_users: frozenset[str]


def _discord_text_only(event: MessageEventLike) -> bool:
    """True only when the event is a real Discord text message we want to gate.

    Non-text events (photo, audio, command) and internal events are passed
    through unmodified — they are not user-authored delete-style requests and
    the gate's regex inference does not apply to them.
    """
    if event.internal:
        return False
    if event.message_type.value != "text":
        return False
    return _platform_value(event.source.platform) == "discord"


def _platform_value(platform: _PlatformLike | str) -> str:
    """``Platform`` enum exposes ``.value``; strings pass through."""
    if isinstance(platform, str):
        return platform.lower()
    return str(getattr(platform, "value", platform) or "").lower()


def _mentions_from_text(text: str) -> tuple[str, ...]:
    """Extract bot identities from a Discord @-mention text.

    NOTE: the verified hermes-agent ``MessageEvent`` exposes ``text``
    only; the raw ``discord.Message`` is on ``raw_message`` (not in
    this plugin's Protocol). Until the operator wires a mention
    extractor, the gate routes on bare @-name prefixes the user
    types (e.g. "@tutor explain X"). The Discord-side
    ``<@USERID>`` parsing is a future extension and intentionally
    left to the VM-side wiring.
    """
    mentions: list[str] = []
    for token in text.split():
        if token.startswith("@") and len(token) > 1:
            mentions.append(token[1:].strip(",.;:").lower())
    return tuple(mentions)


# ---------------------------------------------------------------------------
# Hook callback
# ---------------------------------------------------------------------------


def _dispatch(
    event: MessageEventLike,
    gateway: GatewayLike,
    session_store: SessionStoreLike,
    *,
    home_channel: HomeChannelConfig,
) -> dict[str, Any] | None:
    """``pre_gateway_dispatch`` callback.

    Returns ``None`` (no opinion) or an action dict the gateway understands:

    - ``{"action": "skip"}`` — message ignored; no further dispatch
    - ``{"action": "allow"}`` — fall through to normal agent dispatch
    - ``{"action": "rewrite", "text": "..."}`` — currently not used
    """
    if not _discord_text_only(event):
        # Non-Discord platforms, internal events, non-text messages:
        # the persona gate has no opinion. Let the gateway proceed.
        return None

    discord_msg = DiscordMessage(
        channel_id=str(event.source.chat_id or ""),
        author_id=str(event.source.user_id or ""),
        mentions=_mentions_from_text(event.text),
        content=event.text,
    )
    route: DiscordRoute = route_discord_message(
        discord_msg,
        home_channel_id=home_channel.home_channel_id,
        allowed_users=home_channel.allowed_users,
    )

    if route.ignored:
        return {"action": "skip", "reason": route.reason or "ignored"}
    if route.confirm_required:
        # The confirm_delete branch lives in Ticket 74 (separate
        # issue). The plugin signals "do not dispatch yet" so the
        # operator's interaction handler (#74) can take over.
        return {
            "action": "skip",
            "reason": route.reason or "confirm_delete required",
        }
    if route.decision is Decision.ALLOW:
        return {"action": "allow"}
    # REFUSE_DISCORD: persona refused; surface a brief refusal message
    # to the user so they see why the bot did not respond. Optional
    # refactor: skip this and just return allow, leaving the
    # downstream persona-specific response handler to explain.
    refusal = _format_refusal(route)
    _send_refusal(gateway, event, refusal)
    return {"action": "skip", "reason": route.reason or "refused"}


def _format_refusal(route: DiscordRoute) -> str:
    """Compose a one-line refusal message the user can act on."""
    base = "this persona can't handle that request"
    if route.hint_persona:
        return f"{base}. try @{route.hint_persona}."
    return f"{base}."


def _discord_adapter(gateway: GatewayLike) -> Any:
    """Find the Discord adapter in gateway.adapters regardless of key type.

    hermes-agent stores adapters as Dict[Platform, BasePlatformAdapter],
    keyed by the Platform enum. The enum's .value is the lowercase
    platform name ("discord", "telegram", ...). We scan the keys so
    we do not import Platform at runtime — the plugin stays
    hermes-agent-agnostic. If the key is a string (test fakes, future
    hermes-agent change) we compare directly.
    """
    for key, adapter in gateway.adapters.items():
        if isinstance(key, str):
            if key.lower() == "discord":
                return adapter
        else:
            if str(getattr(key, "value", key) or "").lower() == "discord":
                return adapter
    return None


def _send_refusal(
    gateway: GatewayLike,
    event: MessageEventLike,
    text: str,
) -> None:
    """Best-effort side-channel reply. Sync hook, async adapter.

    The pre_gateway_dispatch hook is invoked synchronously and its
    return value is iterated as an action dict; the gateway does not
    await it. BasePlatformAdapter.send is async def send(...)
    and must not be awaited from sync code — doing so would block the
    loop or leave an unawaited coroutine. We schedule the send on the
    running event loop as a fire-and-forget task (the same pattern
    hermes-agent itself uses for typing indicators and lifecycle
    messages). If no loop is running, we silently skip — the hook
    contract permits a no-op side channel.
    """
    adapter = _discord_adapter(gateway)
    if adapter is None:
        return
    send = getattr(adapter, "send", None)
    if not callable(send):
        return
    chat_id = str(event.source.chat_id or "")

    async def _do_send() -> None:
        try:
            await send(chat_id=chat_id, content=text)
        except (OSError, asyncio.CancelledError):
            # Network/IO failure or gateway shutdown mid-send. Swallow
            # the transport error only — TypeError/AttributeError (bad
            # kwarg, missing method) would indicate an integration bug
            # that the operator must see in logs.
            return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (unit tests, edge cases). Skip the side channel;
        # the hook still returns the documented action dict.
        return
    loop.create_task(_do_send())


# ---------------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------------


def register(
    ctx: PluginContextLike,
    *,
    home_channel: HomeChannelConfig,
) -> None:
    """Standard hermes-agent plugin entry point.

    Captures the operator-provided :class:`HomeChannelConfig` via
    closure so hermes-agent's later call to the hook carries the
    right values without requiring a global. The plugin performs no
    other side effects.
    """

    def _hook(
        event: Any,
        gateway: Any,
        session_store: Any,
        **_kwargs: Any,
    ) -> dict[str, Any] | None:
        return _dispatch(
            event,
            gateway,
            session_store,
            home_channel=home_channel,
        )

    ctx.register_hook("pre_gateway_dispatch", _hook)


__all__: tuple[str, ...] = (
    "HomeChannelConfig",
    "MessageEventLike",
    "PluginContextLike",
    "register",
)
