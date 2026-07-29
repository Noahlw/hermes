from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from hermes.indexer.config import IndexerConfig

log = logging.getLogger(__name__)

# Clone mode recorded for observability
CLONE_MODE_FULL = "full"
CLONE_MODE_PARTIAL = "partial"
CLONE_MODE_SPARSE = "sparse"


@dataclass(frozen=True)
class MirrorState:
    """Observable state of a local git mirror."""

    owner_name: str
    mirror_path: str
    clone_mode: str
    default_branch: str
    pinned_sha: str | None
    last_activity: datetime | None
    disk_bytes: int | None


def _mirror_root(config: IndexerConfig) -> Path:
    return Path(config.mirrors_root)


def _repo_path(owner_name: str, config: IndexerConfig) -> Path:
    """Return the local path for a repo mirror."""
    # Use directory-safe subpath: "owner/name" -> "owner__name"
    safe = owner_name.replace("/", "__")
    return _mirror_root(config) / safe


def clone_url(owner_name: str) -> str:
    """Return the GitHub clone URL for an owner/name."""
    return f"https://github.com/{owner_name}.git"


def active_mirror_path(
    owner_name: str, config: IndexerConfig
) -> Path:
    """Return the active (full-depth) mirror path."""
    return _repo_path(owner_name, config)


def _git(
    args: Sequence[str],
    cwd: str | Path | None = None,
    timeout: int = 300,
) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)!r} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def full_clone(owner_name: str, config: IndexerConfig) -> str:
    """Perform a full-depth clone. Returns the absolute mirror path."""
    dest = active_mirror_path(owner_name, config)
    if dest.exists():
        log.info("Mirror exists at %s, fetching...", dest)
        _git(["fetch", "--all"], cwd=str(dest))
        return str(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)
    url = clone_url(owner_name)
    log.info("Full clone %s -> %s", url, dest)
    _git(["clone", url, str(dest)])
    return str(dest)


def sparse_clone(
    owner_name: str, config: IndexerConfig
) -> str:
    """Perform a shallow/sparse clone for inactive repos. Returns path."""
    dest = active_mirror_path(owner_name, config)
    if dest.exists():
        # Already cloned; convert to shallow/sparse in-place
        log.info("Converting %s to shallow/sparse...", dest)
        _git(
            [
                "fetch",
                "--depth",
                "1",
                "--all",
            ],
            cwd=str(dest),
        )
        # Prune old objects
        _git(["reflog", "expire", "--expire=now", "--all"], cwd=str(dest))
        _git(
            ["gc", "--prune=now", "--aggressive"],
            cwd=str(dest),
            timeout=600,
        )
        return str(dest)
    return full_clone(owner_name, config)


def demote_to_sparse(owner_name: str, config: IndexerConfig) -> str:
    """Demote a full clone to shallow/sparse. Returns path."""
    dest = active_mirror_path(owner_name, config)
    if not dest.exists():
        raise FileNotFoundError(
            f"No mirror found at {dest} for {owner_name}"
        )
    log.info("Demoting %s to shallow...", owner_name)
    # Shallow fetch to reduce depth to 1
    _git(["fetch", "--depth", "1", "--all"], cwd=str(dest))
    # Aggressively prune
    _git(["reflog", "expire", "--expire=now", "--all"], cwd=str(dest))
    _git(["gc", "--prune=now", "--aggressive"], cwd=str(dest), timeout=600)
    return str(dest)


def remove_mirror(owner_name: str, config: IndexerConfig) -> None:
    """Delete the local mirror entirely."""
    dest = active_mirror_path(owner_name, config)
    if dest.exists():
        log.info("Removing mirror at %s", dest)
        shutil.rmtree(str(dest))


def resolve_ref_sha(
    owner_name: str, ref_name: str, config: IndexerConfig
) -> str:
    """Resolve a ref (e.g. 'refs/heads/main') to the current commit SHA."""
    dest = active_mirror_path(owner_name, config)
    if not dest.exists():
        full_clone(owner_name, config)
    raw = _git(["rev-parse", ref_name], cwd=str(dest))
    return raw


def get_repo_default_branch(
    owner_name: str, config: IndexerConfig
) -> str:
    """Get the default branch for a repo from the remote."""
    try:
        dest = active_mirror_path(owner_name, config)
        if dest.exists():
            raw = _git(
                ["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=dest
            )
            if raw:
                # refs/remotes/origin/main -> main
                return raw.removeprefix("refs/remotes/origin/")
    except RuntimeError:
        pass
    return "main"


def list_working_files(
    owner_name: str, commit_sha: str, config: IndexerConfig
) -> list[dict[str, str]]:
    """List files in a specific commit with SHA and path.

    Returns list of {path, sha} dicts.
    """
    dest = active_mirror_path(owner_name, config)
    raw = _git(
        ["ls-tree", "-r", commit_sha], cwd=str(dest), timeout=120
    )
    result: list[dict[str, str]] = []
    for line in raw.splitlines():
        # mode type sha\tpath
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        meta, path = parts
        meta_parts = meta.split(None, 2)
        if len(meta_parts) >= 3:
            result.append({"path": path, "sha": meta_parts[2]})
    return result


def show_file_content(
    owner_name: str, commit_sha: str, path: str, config: IndexerConfig
) -> str:
    """Get file content at a specific commit."""
    dest = active_mirror_path(owner_name, config)
    return _git(
        ["show", f"{commit_sha}:{path}"],
        cwd=str(dest),
        timeout=120,
    )


def diff_files_between(
    owner_name: str,
    before_sha: str,
    after_sha: str,
    config: IndexerConfig,
) -> dict[str, str]:
    """Compare two SHAs and return {path: status} dict.

    Status values: 'added', 'modified', 'deleted', 'renamed'.
    """
    dest = active_mirror_path(owner_name, config)
    raw = _git(
        ["diff", "--name-status", before_sha, after_sha],
        cwd=str(dest),
        timeout=120,
    )
    result: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        status_char = parts[0]
        path = parts[1]
        if status_char == "A":
            result[path] = "added"
        elif status_char == "M":
            result[path] = "modified"
        elif status_char == "D":
            result[path] = "deleted"
        elif status_char.startswith("R"):
            # Renamed: old_path -> new_path
            new_path = parts[2] if len(parts) > 2 else path
            result[new_path] = "renamed"
            result[path] = "deleted"  # old path is gone
        elif status_char == "C":
            result[path] = "added"  # copy treated as added
        else:
            result[path] = "modified"
    return result


def mirror_disk_bytes(owner_name: str, config: IndexerConfig) -> int:
    """Return disk usage of the mirror in bytes."""
    dest = active_mirror_path(owner_name, config)
    if not dest.exists():
        return 0
    try:
        raw = subprocess.run(
            ["du", "-sb", str(dest)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if raw.returncode == 0:
            return int(raw.stdout.split()[0])
    except (ValueError, OSError, subprocess.TimeoutExpired):
        pass
    return 0


def mirror_last_activity(
    owner_name: str, config: IndexerConfig
) -> datetime | None:
    """Return the last git fetch/clone timestamp using the reflog."""
    dest = active_mirror_path(owner_name, config)
    if not dest.exists():
        return None
    try:
        # Use git reflog to find latest activity timestamp
        raw = _git(
            ["reflog", "--date=unix", "--format=%ct", "-1", "--all"],
            cwd=str(dest),
        )
        if raw:
            return datetime.fromtimestamp(int(raw), tz=UTC)
    except (RuntimeError, ValueError):
        pass
    return None


def get_mirror_state(
    owner_name: str, config: IndexerConfig
) -> MirrorState | None:
    """Return observable state for a mirror."""
    dest = active_mirror_path(owner_name, config)
    if not dest.exists():
        return None
    try:
        branch = _git(
            ["rev-parse", "--abbrev-ref", "HEAD"], cwd=dest
        )
        sha = _git(["rev-parse", "HEAD"], cwd=dest)
    except RuntimeError:
        branch = "unknown"
        sha = None
    disk = mirror_disk_bytes(owner_name, config)
    activity = mirror_last_activity(owner_name, config)
    # Detect clone mode heuristically
    mode = CLONE_MODE_FULL
    try:
        depth = _git(
            [
                "rev-list",
                "--count",
                "HEAD",
                "--",
                "--max-count=1",
            ],
            cwd=dest,
        )
        if depth and int(depth) <= 2:
            mode = CLONE_MODE_SPARSE
    except (RuntimeError, ValueError):
        pass
    return MirrorState(
        owner_name=owner_name,
        mirror_path=str(dest),
        clone_mode=mode,
        default_branch=branch or "unknown",
        pinned_sha=sha,
        last_activity=activity,
        disk_bytes=disk,
    )
