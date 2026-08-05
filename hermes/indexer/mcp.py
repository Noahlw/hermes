"""FastMCP server factory for the codebase-knowledge tools.

Ported from ``archive/hermes_agent/mcp_server.py`` without the archived
deps (``MiniMaxClient`` / ``GatewayConfig``). The six data-only tools are
registered on a ``FastMCP`` app that binds to 127.0.0.1 (or a Tailscale
IP) via the constructor ``host``/``port`` — FastMCP decides its
transport-security ``allowed_hosts`` from the constructor ``host``
argument, so a private-interface bind is the socket-level trust
boundary.

The persona contract gate runs per tool call (:func:`route_mcp_tool`),
same as the archived server — non-hermes consumers (e.g. coding agents
over MCP) do not bypass the contract. hermes-agent's own native tools
are registered via :func:`hermes.hermes_agent_plugin.register_indexer_tools`
(also gated).
"""

from __future__ import annotations

from typing import Any

from hermes.indexer import tools as _tools
from hermes.indexer.tools import TOOLS

INSTRUCTIONS: str = (
    "Hermes codebase-knowledge MCP server. Information suite only — "
    "six read tools over the codebase index. Every tool is data-only and "
    "returns the standard MCP response envelope with citation fields; the "
    "client's model grounds and narrates from the returned citations."
)


def create_knowledge_server(
    bind_host: str = "127.0.0.1",
    port: int = 8765,
) -> Any:
    """Construct a FastMCP server named ``hermes-knowledge`` with six tools.

    Binds to *bind_host*:*port* (localhost by default; pass a Tailscale
    IP for remote access). The tools are registered from the shared
    :data:`hermes.indexer.tools.TOOLS` registry, so behaviour is identical
    to the native plugin-tool registration.
    """
    from mcp.server.fastmcp import FastMCP
    from hermes.personas.adapters import route_mcp_tool

    server = FastMCP(
        name="hermes-knowledge",
        instructions=INSTRUCTIONS,
        host=bind_host,
        port=port,
    )

    for name, spec in TOOLS.items():
        handler = spec["handler"]

        server.tool(name=name)(
            _make_tool(handler, name, spec["schema"])
        )

    return server


def _make_tool(fn: Any, tool_name: str, schema: dict[str, Any]) -> Any:
    """Wrap *fn* (a data-only tool) with the persona gate + explicit args.

    FastMCP registers tools by signature introspection, so a ``**kwargs``
    wrapper would surface as a single opaque ``kwargs`` argument. Instead
    the wrapper is generated from the tool's JSON Schema properties, giving
    FastMCP real parameters to validate while the body still runs the
    persona contract gate (:func:`route_mcp_tool`) before the handler.
    """
    from hermes.personas.adapters import route_mcp_tool

    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    _ANN = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "array": "list",
        "object": "dict",
    }

    def _dispatch(**kwargs: Any) -> dict[str, Any]:
        envelope = route_mcp_tool(tool_name)
        if not envelope.get("ok"):
            return envelope
        return fn(**kwargs)

    # Ordered params: required first, then optional (PEP-570 allows no
    # required param after a defaulted one).
    ordered = sorted(
        props.items(),
        key=lambda kv: (kv[0] not in required, kv[0]),
    )
    param_lines: list[str] = []
    arg_names: list[str] = []
    for pname, pinfo in ordered:
        ann = _ANN.get(str(pinfo.get("type", "string")), "Any")
        default = "" if pname in required else " = None"
        param_lines.append(f"    {pname}: {ann}{default},")
        arg_names.append(pname)

    namespace = {"_dispatch": _dispatch, "Any": Any}
    if param_lines:
        kwargs_call = ", ".join(f"{a}={a}" for a in arg_names)
        src = (
            "def _tool(\n"
            + "\n".join(param_lines)
            + f"\n):\n    return _dispatch({kwargs_call})\n"
        )
    else:
        src = "def _tool():\n    return _dispatch()\n"
    exec(src, namespace)  # nameless scope; noqa: S102 — needed for FastMCP introspection
    return namespace["_tool"]


__all__: tuple[str, ...] = ("create_knowledge_server",)