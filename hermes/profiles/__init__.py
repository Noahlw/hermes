"""Profile scaffolding for Hermes V1 persona runtime wiring.

Provides configuration templates and validation for the five hermes-agent
profiles defined by ADR 0003/0004:
  main_agent, assistant, tutor  → Discord-reachable
  librarian, researcher         → MCP-invoked only
"""

from hermes.profiles.config import (
    PROFILE_DEFINITIONS,
    ProfileDefinition,
    ProfileKind,
    generate_config_yaml,
    generate_cron_jobs_json,
    generate_env_file,
    generate_honcho_json,
)
from hermes.profiles.provision import ProvisionPlan, plan_provision

__all__: tuple[str, ...] = (
    "ProfileDefinition",
    "ProfileKind",
    "PROFILE_DEFINITIONS",
    "ProvisionPlan",
    "generate_config_yaml",
    "generate_cron_jobs_json",
    "generate_env_file",
    "generate_honcho_json",
    "plan_provision",
)
