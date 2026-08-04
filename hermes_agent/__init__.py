"""Hermes V1 gateway runtime (D-B fork 2, ADR 0004 amendment, 2026-08-04).

The in-repo ``hermes_agent`` package multiplexes the V1 Discord persona
bots (Assistant, Tutor, Main Agent), the in-process cron scheduler, and
the Tailscale-internal coding-agent MCP server. The policy layer
(``hermes.personas``) is consulted via ``route_discord_message`` /
``route_mcp_tool`` before any dispatch.

This package is the V1 runtime; it is imported by ``python -m hermes_agent``.
"""

from __future__ import annotations

__all__: tuple[str, ...] = (
    "__version__",
)

__version__: str = "0.1.0"