"""MCP server contract tests — gate + error envelopes, no network (map #76 Task 5).

FastMCP 1.2 exposes async ``list_tools`` / ``call_tool`` (``convert_result``
defaults to tuple output; tests force ``convert_result=False`` to get a
``CallToolResult``). Unknown tool names raise ``ToolError`` — V1 OOS actions
are rejected at the transport. The indexer is not configured in tests, so
INDEX_UNAVAILABLE is the real, network-free path for index-backed tools;
``conduct_research`` gets a stub LLM that refuses network.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from hermes_agent.config import GatewayConfig
from hermes_agent.mcp_server import create_mcp_server

EXPECTED_TOOLS = {
    "library_search",
    "knowledge_catalog",
    "expand_citation",
    "impact_map",
    "session_brief",
    "conduct_research",
}

REQUIRED_ENV = {
    "HERMES_HOME": "/tmp/hermes",
    "MINIMAX_API_KEY": "mm-key",
    "DISCORD_HOME_CHANNEL": "1",
    "DISCORD_ALLOWED_USER_ID": "1",
    "DISCORD_BOT_TOKEN_ASSISTANT": "t",
    "DISCORD_BOT_TOKEN_TUTOR": "t",
    "DISCORD_BOT_TOKEN_MAIN_AGENT": "t",
}


class _NoNetworkLLM:
    """LLM stub that refuses network access; gateway must degrade to
    warnings/fallbacks instead of crashing (or calling the API)."""

    def chat(self, *args, **kwargs) -> str:
        raise RuntimeError("no network in tests")


@pytest.fixture()
def server(monkeypatch: pytest.MonkeyPatch) -> object:
    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("INDEXER_CONFIG_PATH", raising=False)
    cfg = GatewayConfig.from_env()
    return create_mcp_server(cfg, _NoNetworkLLM())


def _list_tools(server: object) -> list:
    return asyncio.run(server.list_tools())


def _call_tool(server: object, name: str, args: dict) -> object:
    return asyncio.run(server.call_tool(name, args))


def _payload(result: object) -> dict:
    # FastMCP 1.2 call_tool returns (TextContent-list, dict) for dict outputs.
    return result[1]


def test_all_six_tools_registered(server: object) -> None:
    tools = {t.name for t in _list_tools(server)}
    assert tools == EXPECTED_TOOLS


def test_unregistered_oos_tool_rejected_at_transport(server: object) -> None:
    # V1 OOS actions (generate_plan/execute_plan/push_plan_pr) are not
    # registered as MCP tools — the transport raises ToolError, so no
    # handler and no gateway work ever runs.
    with pytest.raises(Exception, match="generate_plan"):
        _call_tool(server, "generate_plan", {})


def test_knowledge_catalog_without_indexer_returns_index_unavailable(
    server: object,
) -> None:
    # Real path: no INDEXER_CONFIG_PATH -> _load_indexer returns None ->
    # _require_db returns the INDEX_UNAVAILABLE envelope. No network.
    env = _payload(_call_tool(server, "knowledge_catalog", {}))
    assert env["ok"] is False
    assert env["tool"] == "knowledge_catalog"
    assert any(e.get("code") == "INDEX_UNAVAILABLE" for e in env["errors"])


def test_envelope_keys_present_on_error_paths(server: object) -> None:
    env = _payload(_call_tool(
        server,
        "expand_citation",
        {"repo": "a/b", "revision": "main", "path": "x.py",
         "start_line": 1, "end_line": 5},
    ))
    assert env["ok"] is False
    assert set(env) >= {"tool", "data", "warnings", "errors"}
    assert any(e.get("code") == "INDEX_UNAVAILABLE" for e in env["errors"])


def test_conduct_research_gate_ok_but_no_network(server: object) -> None:
    # Gate passes (researcher persona job). With the refusing stub LLM
    # the tool must return an envelope with warnings (degraded), never
    # crash and never hit the network.
    env = _payload(_call_tool(server, "conduct_research", {"topic": "x"}))
    assert env["tool"] == "conduct_research"
    assert "errors" in env and "warnings" in env
