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

import os
from typing import Any

from hermes.hermes_agent_plugin import dispatch as _dispatch

# Toolset name given to the knowledge tools when registered upstream.
INDEXER_TOOLSET: str = "knowledge"

# Kwargs the upstream ``PluginContext.register_tool`` signature accepts,
# beyond the reserved name/toolset/schema/handler/description. Gate-only
# overrides (e.g. ``home_channel``) must never be forwarded to it.
_TOOL_KWARGS: frozenset[str] = frozenset({"emoji", "is_async", "check_fn", "requires_env"})


def _default_home_channel() -> _dispatch.HomeChannelConfig:
    """Build the operator allowlist from the active profile's env.

    hermes-agent calls a plugin's ``register(ctx)`` with only the
    ``PluginContext`` — it never forwards per-profile overrides. The
    operator's home channel and Discord allowlist are therefore read
    from the profile-scoped environment (``DISCORD_HOME_CHANNEL`` /
    ``DISCORD_ALLOWED_USERS``, set per profile in ``.env``), matching
    how the gateway platform itself resolves those values.
    """
    allowed = frozenset(
        u.strip()
        for u in os.environ.get("DISCORD_ALLOWED_USERS", "").split(",")
        if u.strip()
    )
    return _dispatch.HomeChannelConfig(
        home_channel_id=os.environ.get("DISCORD_HOME_CHANNEL", ""),
        allowed_users=allowed,
    )


def register_indexer_tools(ctx: Any, **overrides: Any) -> None:
    """Register the data-only codebase-knowledge tools as native plugin tools.

    Upstream plugin SDK contract (hermes-agent ``hermes_cli/plugins.py``,
    ``PluginContext.register_tool``): ``register_tool(name, toolset,
    schema, handler, ...)`` and the registry invokes each handler as
    ``handler(args, **kwargs)`` where ``args`` is the model-supplied
    argument dict (``tools/registry.py`` ``dispatch``). Each tool here is
    data-only — it queries the codebase index and returns a
    JSON-serializable envelope with citation fields; no LLM client is
    needed, the agent's own model narrates.

    Fails soft on ``ImportError`` so a checkout without ``hermes.indexer``
    still loads the plugin's gate registration. Only ``register_tool``'s
    own kwargs (``emoji``/``is_async``/``check_fn``/``requires_env``) are
    forwarded; a ``toolset`` override is popped first.
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
    forward = {k: v for k, v in overrides.items() if k in _TOOL_KWARGS}

    def _gated(name: str, handler: Any) -> Any:
        """Persona contract gate: route_mcp_tool decides per call.

        Adapts hermes-agent's ``handler(args, **kwargs)`` dispatch to the
        indexer tool handlers' keyword-argument signatures by unpacking the
        ``args`` dict. ``kwargs`` carries extra dispatch context we ignore.
        """

        def _run(args: dict[str, Any] | None = None, **_kwargs: Any) -> dict[str, Any]:
            envelope = route_mcp_tool(name)
            if not envelope.get("ok"):
                return envelope
            return handler(**(args or {}))

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
    to both (e.g. ``home_channel`` for the gate, ``toolset`` for the tools);
    when ``home_channel`` is omitted it is derived from the profile env.
    """
    if "home_channel" not in overrides:
        overrides["home_channel"] = _default_home_channel()
    _dispatch.register(ctx, **overrides)
    register_indexer_tools(ctx, **overrides)