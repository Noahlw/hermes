"""MCP gate-branch + index-success contract tests (reviewer finding 8).

The six V1 tools are all in-contract, so the OUT_OF_SCOPE gate branch
cannot be reached through real gate decisions — these tests force the
branch with a stubbed ``_gate`` to prove the routing code actually
returns the gate envelope verbatim. Success paths run against a fake
``CodebaseIndexDB`` (knowledge_catalog freshness, library_search FTS +
revision filter) so the real tool bodies — not only the error paths —
are covered without a Postgres server.
"""

from __future__ import annotations

import asyncio
import json
import sys
from types import ModuleType
from typing import Any

import pytest

from hermes_agent.config import GatewayConfig
from hermes_agent.mcp_server import _envelope, create_mcp_server

REQUIRED_ENV = {
    "HERMES_HOME": "/tmp/hermes",
    "MINIMAX_API_KEY": "mm-key",
    "DISCORD_HOME_CHANNEL": "1",
    "DISCORD_ALLOWED_USER_ID": "1",
    "DISCORD_BOT_TOKEN_ASSISTANT": "t",
    "DISCORD_BOT_TOKEN_TUTOR": "t",
    "DISCORD_BOT_TOKEN_MAIN_AGENT": "t",
}


class _JsonLLM:
    """LLM stub returning a fixed JSON summary (no network)."""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, **kwargs) -> str:
        self.calls += 1
        return json.dumps({"summary_markdown": "**grounded summary**"})


class _FakeCursor:
    def __init__(self, sha: str, last_success_at=None) -> None:
        self.last_after_sha = sha
        self.last_success_at = last_success_at


class _FakeRepo:
    def __init__(self, repo_id: int, owner_name: str, branch: str, status: str) -> None:
        self.id = repo_id
        self.owner_name = owner_name
        self.default_branch = branch
        self.status = status


class _FakeDB:
    def __init__(self, repos: list[_FakeRepo], hits: list[dict[str, Any]]) -> None:
        self.repos = repos
        self.hits = hits

    def list_active_repos(self) -> list[_FakeRepo]:
        return self.repos

    def get_cursor(self, repo_id: int, ref: str) -> _FakeCursor:
        return _FakeCursor(sha=f"sha-{repo_id}")

    def search_chunks(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.hits[:limit]


def _install_fake_db(monkeypatch: pytest.MonkeyPatch, db: _FakeDB) -> None:
    import hermes_agent.mcp_server as mcp

    def fake_load(config: GatewayConfig):
        return (object(), db)

    monkeypatch.setattr(mcp, "_load_indexer", fake_load)


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch) -> GatewayConfig:
    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("INDEXER_CONFIG_PATH", raising=False)
    return GatewayConfig.from_env()


def _make_server(
    env: GatewayConfig,
    llm: Any,
    *,
    monkeypatch: pytest.MonkeyPatch,
    db: _FakeDB | None = None,
) -> Any:
    if db is not None:
        _install_fake_db(monkeypatch, db)
    return create_mcp_server(env, llm)


def _call_tool(server: Any, name: str, args: dict) -> dict:
    result = asyncio.run(server.call_tool(name, args))
    return result[1]


def test_gate_envelope_returned_verbatim_when_oos(
    env: GatewayConfig, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hermes_agent.mcp_server as mcp

    oos = _envelope(
        tool="knowledge_catalog",
        ok=False,
        errors=[{"code": "OUT_OF_SCOPE", "surface": "mcp", "message": "no"}],
    )
    monkeypatch.setattr(mcp, "_gate", lambda tool_name, misuse_count=0: oos)
    server = _make_server(env, _JsonLLM(), monkeypatch=monkeypatch)
    payload = _call_tool(server, "knowledge_catalog", {})
    # The gate decision must pass through untouched — no db access, no
    # envelope rebuild that could drop fields.
    assert payload == oos


def test_knowledge_catalog_success_with_index(
    env: GatewayConfig, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDB(
        repos=[
            _FakeRepo(1, "a/b", "main", "active"),
            _FakeRepo(2, "c/d", "master", "active"),
        ],
        hits=[],
    )
    server = _make_server(env, _JsonLLM(), monkeypatch=monkeypatch, db=db)
    payload = _call_tool(server, "knowledge_catalog", {})
    assert payload["ok"] is True
    assert payload["job_persona"] == "librarian"
    names = [r["owner_name"] for r in payload["data"]["repos"]]
    assert names == ["a/b", "c/d"]
    assert all(r["sync_sha"] == f"sha-{i + 1}" for i, r in enumerate(payload["data"]["repos"]))


def test_knowledge_catalog_repo_filter_applied(
    env: GatewayConfig, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDB(
        repos=[
            _FakeRepo(1, "a/b", "main", "active"),
            _FakeRepo(2, "c/d", "master", "active"),
        ],
        hits=[],
    )
    server = _make_server(env, _JsonLLM(), monkeypatch=monkeypatch, db=db)
    payload = _call_tool(server, "knowledge_catalog", {"repos": ["a/b"]})
    names = [r["owner_name"] for r in payload["data"]["repos"]]
    assert names == ["a/b"]


def test_library_search_success_summarises_hits(
    env: GatewayConfig, monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _JsonLLM()
    db = _FakeDB(
        repos=[],
        hits=[
            {
                "owner_name": "a/b",
                "commit_sha": "abcdef1234",
                "path": "src/x.py",
                "start_line": 1,
                "end_line": 5,
                "snippet": "def f(): pass",
            }
        ],
    )
    server = _make_server(env, llm, monkeypatch=monkeypatch, db=db)
    payload = _call_tool(
        server, "library_search", {"query": "where is f", "repos": ["a/b"]},
    )
    assert payload["ok"] is True
    assert payload["job_persona"] == "librarian"
    assert payload["data"]["summary_markdown"] == "**grounded summary**"
    assert llm.calls == 1
    assert len(payload["data"]["hits"]) == 1
    assert payload["citations"][0]["path"] == "src/x.py"


def test_library_search_revision_filter_excludes_other_commits(
    env: GatewayConfig, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDB(
        repos=[],
        hits=[
            {
                "owner_name": "a/b",
                "commit_sha": "abc123",
                "path": "src/old.py",
                "start_line": 1,
                "end_line": 1,
                "snippet": "old",
            },
            {
                "owner_name": "a/b",
                "commit_sha": "def456",
                "path": "src/new.py",
                "start_line": 1,
                "end_line": 1,
                "snippet": "new",
            },
        ],
    )
    server = _make_server(env, _JsonLLM(), monkeypatch=monkeypatch, db=db)
    payload = _call_tool(
        server,
        "library_search",
        {"query": "x", "revision": "abc"},
    )
    assert payload["ok"] is True
    paths = [h["citation"]["path"] for h in payload["data"]["hits"]]
    assert paths == ["src/old.py"]


def test_index_guard_wraps_escaping_db_failure(
    env: GatewayConfig, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hermes_agent.mcp_server as mcp

    class _ExplodingDB:
        def list_active_repos(self):
            raise RuntimeError("psycopg2 is missing")

    _install_fake_db(monkeypatch, _ExplodingDB())  # type: ignore[arg-type]
    server = _make_server(env, _JsonLLM(), monkeypatch=monkeypatch)
    payload = _call_tool(server, "knowledge_catalog", {})
    assert payload["ok"] is False
    assert any(e.get("code") == "INDEX_UNAVAILABLE" for e in payload["errors"])
