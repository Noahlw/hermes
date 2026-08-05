"""Gateway runtime configuration loaded from the process environment.

systemd ``EnvironmentFile`` populates ``os.environ`` directly — no
dotenv parsing. ``from_env`` fail-fasts by reporting every required
key that is missing or empty so the operator can see the full list
on one screen (mirrors ``setup/install.sh`` REQUIRED_KEYS validation).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_HONCHO_BASE_URL: str = "http://127.0.0.1:8000"
DEFAULT_MCP_BIND_HOST: str = "127.0.0.1"
DEFAULT_MCP_PORT: int = 8001
DEFAULT_PROFILES_ROOT: str = "~/.hermes/profiles"

# Persona -> token env var name. Matches hermes/profiles/config.py
# PROFILE_DEFINITIONS — kept in this package so the gateway has its own
# V1 Discord-roster manifest independent of any profile reload.
_DISCORD_PERSONA_TOKEN_ENV: dict[str, str] = {
    "assistant": "DISCORD_BOT_TOKEN_ASSISTANT",
    "tutor": "DISCORD_BOT_TOKEN_TUTOR",
    "main_agent": "DISCORD_BOT_TOKEN_MAIN_AGENT",
}


def _env(name: str) -> str:
    """Return ``os.environ[name]`` stripped; empty string for unset/blank."""
    value = os.environ.get(name, "")
    return value.strip()


def _split_csv(value: str) -> frozenset[str]:
    if not value:
        return frozenset()
    return frozenset(part.strip() for part in value.split(",") if part.strip())


@dataclass(frozen=True)
class GatewayConfig:
    """Validated gateway configuration."""

    hermes_home: str
    minimax_api_key: str
    discord_home_channel: str
    discord_allowed_users: frozenset[str]
    discord_tokens: dict[str, str] = field(default_factory=dict)
    honcho_base_url: str = DEFAULT_HONCHO_BASE_URL
    mcp_bind_host: str = DEFAULT_MCP_BIND_HOST
    mcp_port: int = DEFAULT_MCP_PORT
    profiles_root: str = DEFAULT_PROFILES_ROOT
    indexer_config_path: str = ""

    def post_init(self) -> "GatewayConfig":
        """Return a copy with derived paths filled in if blank."""
        return GatewayConfig(
            hermes_home=self.hermes_home,
            minimax_api_key=self.minimax_api_key,
            discord_home_channel=self.discord_home_channel,
            discord_allowed_users=self.discord_allowed_users,
            discord_tokens=dict(self.discord_tokens),
            honcho_base_url=self.honcho_base_url,
            mcp_bind_host=self.mcp_bind_host,
            mcp_port=self.mcp_port,
            profiles_root=(
                os.path.expanduser(self.profiles_root)
                if self.profiles_root
                else DEFAULT_PROFILES_ROOT
            ),
            indexer_config_path=(
                self.indexer_config_path
                or os.path.join(self.hermes_home, "indexer/config.json")
            ),
        )

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        """Load configuration from ``os.environ``.

        Returns a fully validated instance or raises ``ValueError``
        with a multi-line ``missing`` listing.
        """
        cfg = cls(
            hermes_home=_env("HERMES_HOME"),
            minimax_api_key=_env("MINIMAX_API_KEY"),
            discord_home_channel=_env("DISCORD_HOME_CHANNEL"),
            discord_allowed_users=_split_csv(_env("DISCORD_ALLOWED_USER_ID")),
            discord_tokens={
                persona: token
                for persona, env_name in _DISCORD_PERSONA_TOKEN_ENV.items()
                if (token := _env(env_name))
            },
            honcho_base_url=_env("HONCHO_BASE_URL") or DEFAULT_HONCHO_BASE_URL,
            mcp_bind_host=_env("MCP_BIND_HOST") or DEFAULT_MCP_BIND_HOST,
            mcp_port=int(_env("MCP_PORT") or DEFAULT_MCP_PORT),
            profiles_root=_env("PROFILES_ROOT") or DEFAULT_PROFILES_ROOT,
            indexer_config_path=_env("INDEXER_CONFIG_PATH"),
        )
        missing = cfg.missing()
        if missing:
            raise ValueError(
                "GatewayConfig missing required env vars:\n  - "
                + "\n  - ".join(missing)
            )
        return cfg.post_init()

    def missing(self) -> list[str]:
        """Return required env-derived fields that are unset/empty.

        Mirrors ``setup/install.sh`` REQUIRED_KEYS — these are the keys
        the operator MUST supply before the gateway can run.
        """
        missing: list[str] = []
        if not self.hermes_home:
            missing.append("HERMES_HOME")
        if not self.minimax_api_key:
            missing.append("MINIMAX_API_KEY")
        if not self.discord_home_channel:
            missing.append("DISCORD_HOME_CHANNEL")
        if not self.discord_allowed_users:
            missing.append("DISCORD_ALLOWED_USER_ID")
        for persona, env_name in _DISCORD_PERSONA_TOKEN_ENV.items():
            if persona not in self.discord_tokens:
                missing.append(env_name)
        return missing


__all__: tuple[str, ...] = ("GatewayConfig",)