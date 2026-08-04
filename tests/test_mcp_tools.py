"""MCP server contract tests — gate + error envelopes, no network (map #76 Task 5)."""

from __future__ import annotations

import pytest

from hermes_agent.mcp_server import create_mcp_server

EXPECTED_TOOLS = {
    "library_search",
    "knowledge_catalog",
    "expand_citation",
    "impact_map",
    "session_brief",
    "conduct_research",
}


@pytest.fixture()
def server() -> object:
    from hermes_agent.config import GatewayConfig

    cfg = GatewayConfig.from_env(
        {
            "HERMES_HOME": "/tmp/hermes",
            "MINIMAX_API_KEY": "mm-key",
            "DISCORD_HOME_CHANNEL": "1",
            "DISCORD_ALLOWED_USER_ID": "1",
            "DISCORD_BOT_TOKEN_ASSISTANT": "t",
            "DISCORD_BOT_TOKEN_TUTOR": "t",
            "DISCORD_BOT_TOKEN_MAIN_AGENT": "t",
        }
    )
    return create_mcp_server(cfg)


def test_all_six_tools_registered(server: object) -> None:
    tools = {t.name for t in server.list_tools()}
    assert tools == EXPECTED_TOOLS


def test_oos_tool_rejected_with_out_of_scope(server: object) -> None:
    result = server.call_tool("generate_plan", {})
    assert not result.isError
    data = result.content[0].text
    assert '"ok": false' in data
    assert "OUT_OF_SCOPE" in data


def test_mcp_oos_envelope_shape(server: object) -> None:
    result = server.call_tool("generate_plan", {})
    data = result.content[0].text
    assert '"tool": "generate_plan"' in data
    assert '"job_persona"' in data
    assert '"data": null' in data or '"data":' in data
    assert '"errors"' in data
    assert '"code": "OUT_OF_SCOPE"' in data


def test_knowledge_catalog_unavailable_index(server: object) -> None:
    # Real path: point the indexer at a dead config → connection error must
    # surface as INDEX_UNAVAILABLE, not a crash. Monkeypatch the backend so
    # the test stays hermetic (no network).
    import hermes_agent.mcp_server as mcp

    def boom(*args, **kwargs):
        raise RuntimeError("connect failed: dead index")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(mcp, "_index_search", boom)
    try:
        result = server.call_tool("knowledge_catalog", {})
    finally:
        monkeypatch.undo()
    assert not result.isError
    data = result.content[0].text
    assert '"ok": false' in data
    assert '"code": "INDEX_UNAVAILABLE"' in data
