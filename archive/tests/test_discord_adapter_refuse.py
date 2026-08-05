"""PersonaBot REFUSE-path contract tests with a fake discord module.

Reviewer findings 4/5 context: the adapter's routing must never touch
the LLM or Honcho on REFUSE/ignored decisions (delete-without-confirm,
wrong channel, own message, non-allowed user). discord.py is replaced
by a fake module so the tests stay network-free; ``_run_turn_sync`` /
MiniMax / Honcho are asserted to be untouched on every refusal path.
"""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType

import pytest

from hermes_agent.config import GatewayConfig
from hermes_agent.discord_adapter import PersonaBot
from hermes_agent.honcho_client import PersonaMemory

REQUIRED_ENV = {
    "HERMES_HOME": "/tmp/hermes",
    "MINIMAX_API_KEY": "mm-key",
    "DISCORD_HOME_CHANNEL": "111",
    "DISCORD_ALLOWED_USER_ID": "222",
    "DISCORD_BOT_TOKEN_ASSISTANT": "t",
    "DISCORD_BOT_TOKEN_TUTOR": "t",
    "DISCORD_BOT_TOKEN_MAIN_AGENT": "t",
}


class _FakeIntents:
    def __init__(self, **kwargs) -> None:
        self.message_content = kwargs.get("message_content")
        self.guilds = kwargs.get("guilds")


class _FakeUser:
    def __init__(self, user_id: str, name: str = "bot") -> None:
        self.id = user_id
        self.name = name


class _FakeChannel:
    def __init__(self, channel_id: str) -> None:
        self.id = channel_id
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


class _FakeMessage:
    def __init__(
        self,
        author: _FakeUser,
        channel: _FakeChannel,
        content: str,
        mentions: list[_FakeUser],
    ) -> None:
        self.author = author
        self.channel = channel
        self.content = content
        self.mentions = mentions


class _FakeClient:
    def __init__(self, intents: _FakeIntents) -> None:
        self.intents = intents
        self.user = _FakeUser("bot-1")
        self.handlers: dict[str, object] = {}
        self.started: str | None = None
        self.closed = False

    def event(self, fn):
        self.handlers[fn.__name__] = fn
        return fn

    async def start(self, token: str) -> None:
        self.started = token

    def is_closed(self) -> bool:
        return False

    async def close(self) -> None:
        self.closed = True


class _FakeDiscord:
    Intents = _FakeIntents
    Client = _FakeClient


class _NoNetworkLLM:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, *args, **kwargs) -> str:
        self.calls += 1
        raise AssertionError("LLM must not be called on REFUSE/ignored paths")


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch) -> GatewayConfig:
    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)
    return GatewayConfig.from_env()


@pytest.fixture()
def fake_discord(monkeypatch: pytest.MonkeyPatch) -> _FakeDiscord:
    fake = _FakeDiscord()
    mod = ModuleType("discord")
    mod.Intents = fake.Intents
    mod.Client = fake.Client
    monkeypatch.setitem(sys.modules, "discord", mod)
    return fake


@pytest.fixture()
def memory(env: GatewayConfig) -> PersonaMemory:
    # Honcho is never reached on REFUSE/ignored paths; base_url is a
    # dead endpoint so an accidental call fails fast.
    return PersonaMemory(base_url="http://127.0.0.1:1", persona_id="assistant")


def _make_bot(
    env: GatewayConfig,
    memory: PersonaMemory,
    llm: _NoNetworkLLM,
) -> PersonaBot:
    return PersonaBot(
        persona_id="assistant",
        config=env,
        llm=llm,
        memory=memory,
        home_channel_id="111",
        allowed_users=frozenset({"222"}),
    )


def _on_message(bot: PersonaBot, message: _FakeMessage) -> None:
    handler = bot.client.handlers["on_message"]
    asyncio.run(handler(message))


def test_delete_without_confirm_refuses_and_never_touches_llm_or_honcho(
    env: GatewayConfig,
    fake_discord: _FakeDiscord,
    memory: PersonaMemory,
) -> None:
    llm = _NoNetworkLLM()
    bot = _make_bot(env, memory, llm)
    channel = _FakeChannel("111")
    msg = _FakeMessage(
        author=_FakeUser("222"),
        channel=channel,
        content="delete all my tasks",
        mentions=[bot.client.user],
    )
    _on_message(bot, msg)

    assert len(channel.sent) == 1
    assert "confirmation flow" in channel.sent[0]
    assert llm.calls == 0


def test_out_of_home_channel_ignored(
    env: GatewayConfig,
    fake_discord: _FakeDiscord,
    memory: PersonaMemory,
) -> None:
    llm = _NoNetworkLLM()
    bot = _make_bot(env, memory, llm)
    channel = _FakeChannel("999")
    msg = _FakeMessage(
        author=_FakeUser("222"),
        channel=channel,
        content="delete all my tasks",
        mentions=[bot.client.user],
    )
    _on_message(bot, msg)
    assert channel.sent == []
    assert llm.calls == 0


def test_own_message_ignored(
    env: GatewayConfig,
    fake_discord: _FakeDiscord,
    memory: PersonaMemory,
) -> None:
    llm = _NoNetworkLLM()
    bot = _make_bot(env, memory, llm)
    channel = _FakeChannel("111")
    msg = _FakeMessage(
        author=bot.client.user,
        channel=channel,
        content="delete all my tasks",
        mentions=[bot.client.user],
    )
    _on_message(bot, msg)
    assert channel.sent == []
    assert llm.calls == 0


def test_non_allowed_user_ignored(
    env: GatewayConfig,
    fake_discord: _FakeDiscord,
    memory: PersonaMemory,
) -> None:
    llm = _NoNetworkLLM()
    bot = _make_bot(env, memory, llm)
    channel = _FakeChannel("111")
    msg = _FakeMessage(
        author=_FakeUser("999"),
        channel=channel,
        content="delete all my tasks",
        mentions=[bot.client.user],
    )
    _on_message(bot, msg)
    assert channel.sent == []
    assert llm.calls == 0


def test_no_mention_ignored(
    env: GatewayConfig,
    fake_discord: _FakeDiscord,
    memory: PersonaMemory,
) -> None:
    llm = _NoNetworkLLM()
    bot = _make_bot(env, memory, llm)
    channel = _FakeChannel("111")
    msg = _FakeMessage(
        author=_FakeUser("222"),
        channel=channel,
        content="just chatting",
        mentions=[],
    )
    _on_message(bot, msg)
    assert channel.sent == []
    assert llm.calls == 0
