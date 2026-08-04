"""Profile provisioning planner.

Generates a ProvisionPlan — a dry-run manifest of every file that must
be created for each profile.  The plan is idempotent (re-running after
partial success fills only the gaps) and supports both local dev and
remote VM provisioning.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from hermes.profiles.config import (
    DEFAULT_PROFILES_ROOT,
    PROFILE_DEFINITIONS,
    ProfileDefinition,
    generate_config_yaml,
    generate_cron_jobs_json,
    generate_env_file,
    generate_honcho_json,
)

@dataclass(frozen=True)
class _FileEntry:
    """One file the plan must create."""

    rel_path: str
    content: str
    overwrite: bool = False


@dataclass(frozen=True)
class _DirEntry:
    """One directory the plan must create."""

    rel_path: str


@dataclass(frozen=True)
class ProvisionPlan:
    """Idempotent provisioning manifest for a set of profiles.

    ``root`` is the profiles directory (default ~/.hermes/profiles).
    ``entries`` lists every file and directory to create, in dependency
    order (parents before children).
    """

    root: str
    profiles: Mapping[str, ProfileDefinition]
    dirs: tuple[str, ...]
    files: tuple[tuple[str, str], ...]  # (rel_path, content) pairs

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def dir_count(self) -> int:
        return len(self.dirs)

    def validate(self) -> list[str]:
        """Check the plan for correctness before applying.

        Returns a list of error messages (empty = valid).
        """
        errors: list[str] = []
        seen_profile_ids: set[str] = set()
        for persona_id, profile in self.profiles.items():
            if persona_id != profile.persona_id:
                errors.append(
                    f"Key '{persona_id}' does not match ProfileDefinition.persona_id "
                    f"'{profile.persona_id}'"
                )
            if persona_id in seen_profile_ids:
                errors.append(f"Duplicate persona_id: {persona_id}")
            seen_profile_ids.add(persona_id)
        if not self.profiles:
            errors.append("Plan contains no profiles")
        # All entry paths must be under root.
        for d in self.dirs:
            if not d.startswith(self.root):
                errors.append(f"Directory '{d}' is not under root '{self.root}'")
        for rel_path, _content in self.files:
            full = os.path.join(self.root, rel_path)
            if not full.startswith(self.root):
                errors.append(f"File '{full}' is not under root '{self.root}'")
        return errors


def plan_provision(
    persona_ids: frozenset[str] | None = None,
    root: str = DEFAULT_PROFILES_ROOT,
) -> ProvisionPlan:
    """Build an idempotent provisioning plan.

    If *persona_ids* is None, provision all five V1 profiles.
    """
    if persona_ids is None:
        persona_ids = frozenset(PROFILE_DEFINITIONS)

    profiles: dict[str, ProfileDefinition] = {}
    for pid in sorted(persona_ids):
        if pid not in PROFILE_DEFINITIONS:
            raise ValueError(
                f"Unknown persona_id '{pid}'. "
                f"Valid: {sorted(PROFILE_DEFINITIONS)}"
            )
        profiles[pid] = PROFILE_DEFINITIONS[pid]

    dirs: list[str] = []
    files: list[tuple[str, str]] = []

    # Each profile gets its own directory tree.
    subdirs = ("memory", "sessions", "skills", "cron/logs", "logs/cron")
    for profile in profiles.values():
        home = os.path.join(root, profile.persona_id)
        dirs.append(home)
        for sd in subdirs:
            dirs.append(os.path.join(home, sd))

        # Config files — always provisioned.
        files.append((
            os.path.join(profile.persona_id, "config.yaml"),
            generate_config_yaml(profile),
        ))
        files.append((
            os.path.join(profile.persona_id, ".env"),
            generate_env_file(profile),
        ))
        files.append((
            os.path.join(profile.persona_id, "honcho.json"),
            generate_honcho_json(profile),
        ))
        files.append((
            os.path.join(profile.persona_id, "cron", "jobs.json"),
            generate_cron_jobs_json(profile, root),
        ))

    return ProvisionPlan(
        root=root,
        profiles=profiles,
        dirs=tuple(dirs),
        files=tuple(files),
    )
