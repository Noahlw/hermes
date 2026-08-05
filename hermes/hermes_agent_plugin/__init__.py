"""hermes-agent plugin entry point for the persona contract gate.

This package is a thin adapter that connects hermes-agent's
``pre_gateway_dispatch`` hook to this repo's persona policy layer. It
is shipped as a separate module so its hermes-agent-specific code
lives next to the policy it wraps, but stays out of the policy module
itself (which must remain hermes-agent-agnostic).

External (SSH-gated) deployment steps to wire this plugin to a live
hermes-agent are tracked in the parent issue; the source in this
package is fully testable in this repo with no hermes-agent
dependency.

The plugin's :func:`register` entry point keeps the persona-contract-gate
registration intact (via :mod:`hermes.hermes_agent_plugin.dispatch`) and
additionally registers the data-only codebase-knowledge tools
(:func:`register_indexer_tools`) as native upstream tools.
"""

from __future__ import annotations

from typing import Any

from hermes.hermes_agent_plugin import dispatch as _dispatch

# Toolset name given to the knowledge tools when registered upstream.
INDEXER_TOOLSET: str = "knowledge"


def register_indexer_tools(ctx: Any, **overrides: Any) -> None:
    """Register the data-only codebase-knowledge tools as native plugin tools.

    Upstream plugin SDK contract (hermes-agent ``hermes_cli/plugins.py``,
    ``PluginContext.register_tool``): ``register_tool(name, toolset,
    schema, handler, ...)``. Each tool here is data-only — it queries the
    codebase index and returns a JSON-serializable envelope with citation
    fields; no LLM client is needed, the agent's own model narrates.

    Fails soft on ``ImportError`` so a checkout without ``hermes.indexer``
    still loads the plugin's gate registration. Extra ``overrides`` are
    forwarded to ``register_tool`` (e.g. ``emoji``, ``is_async``); reserved
    per-tool keys (``name``/``toolset``/``schema``/``handler``/``description``)
    and a ``toolset`` override are popped first.
    """
    try:
        from hermes.indexer import tools as _tools
        from hermes.personas.adapters import route_mcp_tool
    except ImportError:
        return

    register_tool = getattr(ctx, "register_tool", None)
    if not callable(register_tool):
        return

    toolset = overrides.pop("toolset", INDEXER_TOOLSET)
    forward = {
        k: v
        for k, v in overrides.items()
        if k not in {"name", "toolset", "schema", "handler", "description"}
    }

    def _gated(name: str, handler: Any) -> Any:
        """Persona contract gate: route_mcp_tool decides per call."""

        def _run(**kwargs: Any) -> dict[str, Any]:
            envelope = route_mcp_tool(name)
            if not envelope.get("ok"):
                return envelope
            return handler(**kwargs)

        return _run

    for name, spec in _tools.TOOLS.items():
        register_tool(
            name=name,
            toolset=toolset,
            schema=spec["schema"],
            handler=_gated(name, spec["handler"]),
            description=spec.get("description", ""),
            **forward,
        )


def register(ctx: Any, **overrides: Any) -> None:
    """Standard hermes-agent plugin entry point.

    Keeps the persona-contract-gate registration intact by delegating to
    :func:`hermes.hermes_agent_plugin.dispatch.register`
    (``pre_gateway_dispatch`` hook), then registers the data-only
    codebase-knowledge tools as native tools. ``overrides`` are forwarded
    to both (e.g. ``home_channel`` for the gate, ``toolset`` for the tools).
    """
    _dispatch.register(ctx, **overrides)
    register_indexer_tools(ctx, **overrides)