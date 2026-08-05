"""Persona-to-profile roster and legacy provisioning templates.

The roster (persona_id - ProfileDefinition, Discord env names, home
channel) is the single source of truth for persona-bot mapping.
The provisioning helpers target the ARCHIVED private runtime's config
shape ("adapters: discord ...", ``enable_cron``, own HERMES_HOME dirs)
- ADR 0007 pivot: reference only. Upstream profiles are provisioned per
AGENTS.md Step 2b (``hermes profile create`` + per-profile
``~/.hermes/profiles/<name>/.env`` with ``DISCORD_BOT_TOKEN``); persona
memory isolation comes from upstream Honcho host blocks, not per-dir
HOME.
"""

from __future__ import annotations

import enum
import json
import os
from dataclasses import dataclass, field


DEFAULT_PROFILES_ROOT = os.path.expanduser("~/.hermes/profiles")


class ProfileKind(str, enum.Enum):
    DISCORD = "discord"
    MCP = "mcp"


@dataclass(frozen=True)
class ProfileDefinition:
    """Immutable definition of one hermes-agent profile.

    Loaded from PROFILE_DEFINITIONS; never mutated at runtime.  The
    gateway's multiplex layer reads these to know which profiles to
    serve, which adapters each enables, and how to route mentions.
    """

    persona_id: str
    kind: ProfileKind
    home_channel: str | None = None
    enable_discord: bool = False
    enable_cron: bool = False
    discord_bot_token_env: str = ""

    def __post_init__(self) -> None:
        if self.kind == ProfileKind.DISCORD:
            if not self.enable_discord:
                raise ValueError(
                    f"Discord profile '{self.persona_id}' must have enable_discord=True"
                )
            if not self.discord_bot_token_env:
                raise ValueError(
                    f"Discord profile '{self.persona_id}' must set discord_bot_token_env"
                )
        if self.kind == ProfileKind.MCP and self.enable_discord:
            raise ValueError(
                f"MCP profile '{self.persona_id}' must not enable Discord"
            )


# Fixed V1 roster (ADR 0003).  Only these five persona_ids are valid.
PROFILE_DEFINITIONS: dict[str, ProfileDefinition] = {
    "main_agent": ProfileDefinition(
        persona_id="main_agent",
        kind=ProfileKind.DISCORD,
        home_channel="DISCORD_HOME_CHANNEL",
        enable_discord=True,
        enable_cron=True,
        discord_bot_token_env="DISCORD_BOT_TOKEN_MAIN_AGENT",
    ),
    "assistant": ProfileDefinition(
        persona_id="assistant",
        kind=ProfileKind.DISCORD,
        home_channel="DISCORD_HOME_CHANNEL",
        enable_discord=True,
        enable_cron=False,
        discord_bot_token_env="DISCORD_BOT_TOKEN_ASSISTANT",
    ),
    "tutor": ProfileDefinition(
        persona_id="tutor",
        kind=ProfileKind.DISCORD,
        home_channel="DISCORD_HOME_CHANNEL",
        enable_discord=True,
        enable_cron=False,
        discord_bot_token_env="DISCORD_BOT_TOKEN_TUTOR",
    ),
    "librarian": ProfileDefinition(
        persona_id="librarian",
        kind=ProfileKind.MCP,
        enable_discord=False,
        enable_cron=False,
    ),
    "researcher": ProfileDefinition(
        persona_id="researcher",
        kind=ProfileKind.MCP,
        enable_discord=False,
        enable_cron=False,
    ),
}


def generate_config_yaml(profile: ProfileDefinition) -> str:
    """Generate a hermes-agent config.yaml for *profile*.

    Multiplex profiles each get their own config; the gateway's
    multiplex_profiles setting in the primary profile's config tells
    hermes-agent to serve all of them.
    """
    lines = [
        "# Hermes V1 profile config — managed by Hermes repo provisioning.",
        f"# Profile: {profile.persona_id}",
        "# Do not edit by hand on the VM.",
        "",
        "gateway:",
        "  multiplex_profiles: true",
        "",
    ]
    if profile.enable_discord:
        lines.extend([
            "adapters:",
            "  discord:",
            f"    home_channel: {profile.home_channel}",
            "    bot_name: hermes_bot",
            "    required_mention: true",
            "",
        ])
    if profile.enable_cron:
        lines.extend([
            "cron:",
            "  enabled: true",
            "  scheduler: in_process",
            "",
        ])
    return "\n".join(lines)


def generate_env_file(profile: ProfileDefinition) -> str:
    """Generate a .env file for *profile*.

    Secrets (tokens) are placeholders replaced during deploy.  The
    operator MUST supply real values before the profile is served.
    """
    lines = [
        f"# Hermes V1 profile env — {profile.persona_id}",
        "# Replace PLACEHOLDER values before serving.",
        "",
    ]
    if profile.enable_discord:
        token_placeholder = (
            "PLACEHOLDER_DISCORD_BOT_TOKEN"  # pragma: allowlist secret
        )
        lines.append(
            f'{profile.discord_bot_token_env}="{token_placeholder}"'
        )
        lines.append('DISCORD_ALLOWED_USERS="PLACEHOLDER_COMMA_SEPARATED_USER_IDS"')
    return "\n".join(lines) + "\n"


def generate_honcho_json(profile: ProfileDefinition) -> str:
    """Generate honcho.json for *profile*.

    Each persona resolves a distinct ai_peer identity and workspace_id
    so cross-profile memory reads are blocked at the Honcho backend.
    """
    config = {
        "_comment": f"Hermes V1 Honcho config — {profile.persona_id}",
        "ai_peer": f"hermes_{profile.persona_id}",
        "workspace_id": f"hermes_{profile.persona_id}",
    }
    return json.dumps(config, indent=2) + "\n"


# Default cron jobs for main_agent profile (Ticket 72 § Ticket 3).
# The ops-digest job is added during provisioning alongside existing
# VM-wide cron entries.  log_file is derived from the provision root so
# jobs.json never embeds a machine-specific absolute path.
def generate_cron_jobs_json(
    profile: ProfileDefinition, root: str = DEFAULT_PROFILES_ROOT
) -> str:
    """Generate cron/jobs.json for *profile*.

    Only main_agent runs the ops-digest cron job in V1; other profiles
get an empty jobs array.  ``root`` is the profiles directory being
provisioned (see hermes.profiles.provision); the ops-digest log path
resolves under it.
    """
    jobs: list[dict[str, object]] = []
    if profile.persona_id == "main_agent":
        jobs = [
    {
        "id": "ops-digest",
        "name": "Daily ops digest",
        "enabled": True,
        "command": "hermes-digest",
        "schedule": "0 7 * * *",
        "args": ["--window", "24h"],
                "log_file": os.path.join(
                    root, profile.persona_id, "logs", "cron", "ops-digest.log"
                ),
    },
]
    doc = {
        "_comment": f"Hermes V1 cron jobs — {profile.persona_id}.",
        "_note": "Managed by hermes-agent InProcessCronScheduler.",
        "jobs": jobs,
    }
    return json.dumps(doc, indent=2) + "\n"
