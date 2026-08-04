"""Discord adapter — one ``PersonaBot`` per V1 Discord persona.

The gateway multiplexes three bots (Assistant, Tutor, Main Agent) on
the shared home channel. Every inbound message runs through the policy
layer (``route_discord_message``); ALLOW replies are MiniMax-narrated
turns grounded in Honcho memory. All Honcho + MiniMax calls run on
``asyncio.to_thread`` to keep the discord.py event loop unblocked.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from hermes.personas.adapters import (
    Decision,
    DiscordMessage,
    DiscordRoute,
    route_discord_message,
)
from hermes.personas.contract_gate import load_contracts

from hermes_agent.config import GatewayConfig
from hermes_agent.honcho_client import PersonaMemory
from hermes_agent.llm import MiniMaxClient, persona_system_prompt

logger = logging.getLogger("hermes_agent")


def _persona_id_for_bot(client_user: Any) -> str | None:
    """Reverse the Discord mention back into a persona_id.

    The bot's ``display_name`` is the only stable field across guilds,
    so we normalize lowercase. Returns ``None`` when the bot display
    name does not match one of the V1 Discord personas — caller
    silently drops the message in that case.
    """
    name = getattr(client_user, "name", "") or ""
    normalized = name.strip().lower()
    # V1 mapping is name -> persona_id. Display names follow the
    # ``hermes-<persona>`` convention used by setup/gateway.sh.
    suffix = normalized.rsplit("-", 1)[-1] if "-" in normalized else normalized
    if suffix in {"assistant", "tutor", "main_agent"}:
        return suffix
    if normalized in {"assistant", "tutor", "main_agent"}:
        return normalized
    return None


class PersonaBot:
    """One discord.py ``Client`` instance per V1 Discord persona."""

    def __init__(
        self,
        persona_id: str,
        config: GatewayConfig,
        llm: MiniMaxClient,
        memory: PersonaMemory,
        home_channel_id: str,
        allowed_users: frozenset[str],
    ) -> None:
        # Lazy import — discord.py pulls aiohttp and other heavy deps
        # only when the bot actually starts.
        import discord

        intents = discord.Intents(message_content=True, guilds=True)
        self._client = discord.Client(intents=intents)
        self._persona_id = persona_id
        self._config = config
        self._llm = llm
        self._memory = memory
        self._home_channel_id = home_channel_id
        self._allowed_users = allowed_users
        self._contracts = load_contracts()
        self._system_prompt = persona_system_prompt(persona_id, self._contracts)
        self._user: Any | None = None
        self._wire_handlers()

    @property
    def client(self) -> Any:
        return self._client

    @property
    def persona_id(self) -> str:
        return self._persona_id

    # -- discord wiring ----------------------------------------------------

    def _wire_handlers(self) -> None:
        client = self._client

        @client.event
        async def on_ready() -> None:  # type: ignore[no-redef]
            self._user = client.user
            uid = getattr(self._user, "id", "?") if self._user else "?"
            name = getattr(self._user, "name", "?") if self._user else "?"
            logger.info(
                "[gateway] %s logged in as %s (id %s)",
                self._persona_id,
                name,
                uid,
            )

        @client.event
        async def on_message(message: Any) -> None:  # type: ignore[no-redef]
            await self._handle_message(message)

    # -- message handling --------------------------------------------------

    async def _handle_message(self, message: Any) -> None:
        # Ignore our own messages.
        if message.author == self._client.user:
            return
        # Identify which bot was @-mentioned by inspecting the mentions
        # list. discord.py resolves ``client.user`` against ``message.mentions``.
        mentioned_bots = [m for m in message.mentions if m == self._client.user]
        if not mentioned_bots:
            return
        persona_id = _persona_id_for_bot(self._client.user) or self._persona_id

        dm = DiscordMessage(
            channel_id=str(message.channel.id),
            author_id=str(message.author.id),
            mentions=(persona_id,),
            content=message.content or "",
            confirm_delete=False,
        )
        route = route_discord_message(
            dm,
            self._home_channel_id,
            self._allowed_users,
        )

        if route.ignored:
            return

        if route.decision == Decision.REFUSE_DISCORD:
            await self._reply_refuse(message, route)
            return

        if route.decision == Decision.ALLOW:
            await self._reply_turn(message, dm, route)
            return

        # Unknown decision (e.g. future enum value) — log and ignore.
        logger.warning(
            "[gateway] %s unknown route decision %r — ignoring",
            self._persona_id,
            route.decision,
        )

    async def _reply_refuse(self, message: Any, route: DiscordRoute) -> None:
        parts: list[str] = [route.reason or "Out of scope."]
        if route.hint_persona:
            parts.append(f"Try @{route.hint_persona}.")
        if route.confirm_required:
            parts.append(
                "Delete requires a confirmation flow that V1 ships later "
                "(CONTEXT.md confirm_delete UX)."
            )
        await message.channel.send("\n".join(parts))

    async def _reply_turn(
        self,
        message: Any,
        dm: DiscordMessage,
        route: DiscordRoute,
    ) -> None:
        persona_id = route.persona_id or self._persona_id
        try:
            reply = await asyncio.to_thread(
                self._run_turn_sync, dm.content, dm.author_id
            )
        except Exception:  # noqa: BLE001 — surface as Discord text + log traceback
            logger.exception(
                "[gateway] %s turn failed", persona_id,
            )
            await message.channel.send(
                "Sorry — the persona hit an internal error. "
                "The operator has been notified."
            )
            return
        if not reply:
            reply = "(empty response)"
        # Discord has a 2000-char message cap. Chunk defensively.
        for chunk in _chunk_for_discord(reply):
            await message.channel.send(chunk)

    # -- sync turn (called on a worker thread) -----------------------------

    def _run_turn_sync(self, user_text: str, author_id: str) -> str:
        """Run a full Honcho-then-MiniMax-then-Honcho turn synchronously."""
        user_peer_id = self._memory.bind_user(author_id)
        self._memory.ensure_session()
        history = self._memory.recent_messages(limit=20)

        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt},
        ]
        for row in history:
            role = row.get("role", "user")
            content = row.get("content", "")
            if not content:
                continue
            if role == "ai":
                role = "assistant"
            elif role not in {"system", "user", "assistant"}:
                role = "user"
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_text})

        raw = self._llm.chat(messages)
        reply = raw.strip()
        # Persist the exchange to Honcho so the next turn has context.
        try:
            self._memory.add_user(user_text, user_peer_id=user_peer_id)
            self._memory.add_ai(reply)
        except Exception:  # noqa: BLE001
            logger.exception(
                "[gateway] %s honcho persist failed", self._persona_id,
            )
        return reply

    # -- lifecycle ---------------------------------------------------------

    async def start(self, token: str) -> None:
        await self._client.start(token)

    async def close(self) -> None:
        if not self._client.is_closed():
            await self._client.close()


def _chunk_for_discord(text: str, limit: int = 1900) -> list[str]:
    """Split *text* into Discord-friendly chunks (≤*limit* chars).

    Prefers splitting on paragraph / line / word boundaries; falls back
    to hard splits for giant single-token blobs. The 1900 default leaves
    headroom for ``message.channel.send`` formatting.
    """
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        # Prefer newline split.
        cut = remaining.rfind("\n", 0, limit)
        if cut == -1 or cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut == -1 or cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        chunks.append(remaining)
    return chunks


class DiscordGateway:
    """Owns the three V1 Discord PersonaBot instances.

    ``start`` is a coroutine that runs ``bot.start(token)`` for each
    bot concurrently and returns when any bot stops (the rest are then
    closed in ``close``). This shape matches what ``main.py`` expects
    for the asyncio.gather multiplexing pattern.
    """

    def __init__(
        self,
        config: GatewayConfig,
        llm: MiniMaxClient,
    ) -> None:
        self._config = config
        self._llm = llm
        self._bots: dict[str, PersonaBot] = {}
        self._start_tasks: list[asyncio.Task[None]] = []

    @property
    def bots(self) -> dict[str, PersonaBot]:
        return dict(self._bots)

    def _build_bots(self) -> None:
        # honcho_base_url is per-config — every persona shares it.
        for persona_id in sorted(self._config.discord_tokens):
            memory = PersonaMemory(
                base_url=self._config.honcho_base_url,
                persona_id=persona_id,
                profiles_root=self._config.profiles_root,
            )
            bot = PersonaBot(
                persona_id=persona_id,
                config=self._config,
                llm=self._llm,
                memory=memory,
                home_channel_id=self._config.discord_home_channel,
                allowed_users=self._config.discord_allowed_users,
            )
            self._bots[persona_id] = bot

    async def start(self) -> None:
        if not self._bots:
            self._build_bots()
        tokens = self._config.discord_tokens
        if not tokens:
            raise RuntimeError(
                "DiscordGateway: no Discord tokens configured "
                "(DISCORD_BOT_TOKEN_ASSISTANT/TUTOR/MAIN_AGENT)"
            )
        loop = asyncio.get_running_loop()
        self._start_tasks = []
        for persona_id, bot in self._bots.items():
            token = tokens.get(persona_id, "")
            if not token:
                logger.warning(
                    "[gateway] no token for persona %s — skipping", persona_id,
                )
                continue
            self._start_tasks.append(loop.create_task(bot.start(token)))
        if not self._start_tasks:
            raise RuntimeError("DiscordGateway: no bots started (all tokens empty)")

    async def wait(self) -> None:
        """Wait for any bot task to finish and surface its outcome.

        ``bot.start(token)`` returns only when a bot disconnects or is
        closed, and raises when login fails (bad/revoked token). Callers
        (``main._run_multiplex``) race this against the stop event so a
        dead bot tears the gateway down for systemd to restart — it
        must never silently reduce the bot count.
        """
        if not self._start_tasks:
            return
        done, _pending = await asyncio.wait(
            set(self._start_tasks), return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            exc = task.exception()
            if exc is not None:
                raise RuntimeError(f"discord bot task failed: {exc}") from exc
        # A bot disconnected cleanly — treat as gateway degradation too.
        raise RuntimeError("a discord bot stopped unexpectedly")

    async def close(self) -> None:
        for task in self._start_tasks:
            if not task.done():
                task.cancel()
        for bot in self._bots.values():
            try:
                await bot.close()
            except Exception:  # noqa: BLE001
                logger.exception("[gateway] bot close failed")
        # Drain cancellations to avoid "Task was destroyed but pending" warnings.
        for task in self._start_tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


__all__: tuple[str, ...] = (
    "DiscordGateway",
    "PersonaBot",
)


# Type-checking placeholders — kept so the import surface is stable
# even if the discord.py Client type is imported lazily elsewhere.
_ = Awaitable
_ = Callable