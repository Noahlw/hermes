"""PersonaMemory explicit-peer contract tests with a fake honcho SDK.

Reviewer finding 4: concurrent ``asyncio.to_thread`` turns share the
mutable ``_user_peer_id`` instance field, so a second ``bind_user`` can
cross-attribute the first turn's message. The fix is the explicit
``user_peer_id`` parameter on ``add_user``; these tests pin that
contract: attribution follows the per-call peer id, never the shared
instance state, and ``recent_messages`` still maps peers to
user/ai roles.

The real honcho SDK is never imported — a fake ``honcho`` module is
injected into ``sys.modules`` (PersonaMemory imports honcho lazily).
"""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from hermes_agent.honcho_client import PersonaMemory


class _FakeMsg:
    def __init__(self, peer_id: str, content: str) -> None:
        self.peer_id = peer_id
        self.content = content


class _FakePeer:
    def __init__(self, peer_id: str) -> None:
        self.id = peer_id
        self.messages: list[_FakeMsg] = []

    def message(self, text: str) -> _FakeMsg:
        msg = _FakeMsg(self.id, text)
        self.messages.append(msg)
        return msg


class _FakeSession:
    def __init__(self) -> None:
        self.id = "sess-1"
        self.messages_log: list[_FakeMsg] = []

    def add_messages(self, messages: list[_FakeMsg]) -> None:
        self.messages_log.extend(messages)

    def messages(self, reverse: bool = False, size: int = 20) -> list[_FakeMsg]:
        ordered = list(self.messages_log)
        if reverse:
            ordered.reverse()
        return ordered[: max(1, int(size))]


class _FakeHoncho:
    instances: list["_FakeHoncho"] = []

    def __init__(self, workspace_id: str, base_url: str = "", api_key: str = "") -> None:
        self.workspace_id = workspace_id
        self.base_url = base_url
        self.api_key = api_key
        self.peers: dict[str, _FakePeer] = {}
        self.sessions: dict[str, _FakeSession] = {}
        self.instantiated = True
        _FakeHoncho.instances.append(self)

    def peer(self, peer_id: str) -> _FakePeer:
        return self.peers.setdefault(peer_id, _FakePeer(peer_id))

    def session(self, name: str) -> _FakeSession:
        return self.sessions.setdefault(name, _FakeSession())


def _install_fake_honcho(monkeypatch: pytest.MonkeyPatch) -> _FakeHoncho:
    _FakeHoncho.instances.clear()
    fake = _FakeHoncho(workspace_id="hermes_assistant")
    mod = ModuleType("honcho")
    mod.Honcho = fake.__class__
    monkeypatch.setitem(sys.modules, "honcho", mod)
    return fake


def _honcho_used_by_memory() -> _FakeHoncho:
    """The instance PersonaMemory actually constructed (via Honcho(**kw))."""
    return _FakeHoncho.instances[-1]


def _memory(
    monkeypatch: pytest.MonkeyPatch, fake: _FakeHoncho,
) -> PersonaMemory:
    # base_url points nowhere but is never reached — Honcho is faked.
    return PersonaMemory(
        base_url="http://127.0.0.1:1",
        persona_id="assistant",
        profiles_root="/tmp/hermes/profiles",
    )


def test_honcho_instantiated_with_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install_fake_honcho(monkeypatch)
    memory = _memory(monkeypatch, fake)
    # _ensure_honcho is lazy; binding a user forces instantiation.
    memory.bind_user("42")
    assert fake.instantiated
    assert fake.workspace_id == "hermes_assistant"


def test_add_user_without_peer_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install_fake_honcho(monkeypatch)
    memory = _memory(monkeypatch, fake)
    with pytest.raises(RuntimeError, match="before bind_user"):
        memory.add_user("hello")


def test_add_user_explicit_peer_attributes_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_honcho(monkeypatch)
    memory = _memory(monkeypatch, _honcho_used_by_memory())
    # The concurrent-turn contract: attribution follows the explicit
    # peer id even when the shared instance field points elsewhere.
    memory.add_user("message from 42", user_peer_id="discord_user_42_assistant")
    session = _honcho_used_by_memory().sessions["discord"]
    assert len(session.messages_log) == 1
    assert session.messages_log[0].peer_id == "discord_user_42_assistant"


def test_concurrent_peers_do_not_cross_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_honcho(monkeypatch)
    memory = _memory(monkeypatch, _honcho_used_by_memory())
    memory.bind_user("42")
    memory.add_user("from 42")
    # Second turn binds a different author and attributes its own
    # message — the first message must keep its original peer.
    memory.bind_user("99")
    memory.add_user("from 99")
    used = _honcho_used_by_memory()
    peers = {m.peer_id for m in used.sessions["discord"].messages_log}
    assert peers == {"discord_user_42_assistant", "discord_user_99_assistant"}
    contents = [m.content for m in used.sessions["discord"].messages_log]
    assert contents == ["from 42", "from 99"]


def test_ai_and_user_roles_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install_fake_honcho(monkeypatch)
    memory = _memory(monkeypatch, fake)
    memory.add_user("hello", user_peer_id="discord_user_42_assistant")
    memory.add_ai("hi there")
    rows = memory.recent_messages(limit=20)
    assert [(r["role"], r["content"]) for r in rows] == [
        ("user", "hello"),
        ("ai", "hi there"),
    ]


def test_recent_messages_oldest_first_with_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeHoncho.instances[0]
    fake = _install_fake_honcho(monkeypatch)
    memory = _memory(monkeypatch, fake)
    for i in range(5):
        memory.add_user(f"u{i}", user_peer_id=f"discord_user_{i}_assistant")
        memory.add_ai(f"a{i}")
    rows = memory.recent_messages(limit=2)
    # size=2 fetches the two newest (u4/a4); rows.reverse() then makes
    # the window oldest-first — u3/a3 fall outside the fetched window.
    assert [r["content"] for r in rows] == ["u4", "a4"]


def test_empty_text_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_honcho(monkeypatch)
    memory = _memory(monkeypatch, _honcho_used_by_memory())
    memory.add_user("", user_peer_id="discord_user_42_assistant")
    memory.add_ai("")
