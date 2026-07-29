from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AllowlistEntry:
    """One allowlisted repository with optional extra refs."""

    owner_name: str  # "owner/name"
    extra_refs: tuple[str, ...] = ()

    def validate(self) -> None:
        if "/" not in self.owner_name or self.owner_name.count("/") != 1:
            raise ValueError(
                f"owner_name must be 'owner/name', got {self.owner_name!r}"
            )
        owner, name = self.owner_name.split("/", 1)
        if not owner or not name:
            raise ValueError(
                f"owner_name parts must be non-empty, got {self.owner_name!r}"
            )


@dataclass(frozen=True)
class IndexerConfig:
    """Config loaded from a JSON file."""

    allowlist: tuple[AllowlistEntry, ...]
    mirrors_root: str = "/home/ubuntu/.hermes/mirrors"
    webhook_secret: str = ""
    webhook_port: int = 8080
    webhook_rate_limit: int = 60  # requests per minute
    reconcile_interval_minutes: int = 60
    inactive_days: int = 14
    inactive_pool_gb: int = 80
    db_host: str = "127.0.0.1"
    db_port: int = 5433
    db_name: str = "codebase_index"
    db_user: str = "postgres"
    db_password: str = ""
    excluded_paths: tuple[str, ...] = (
        ".env",
        ".env.*",
        "__pycache__",
        "*.pyc",
        "node_modules",
        "vendor",
        ".git",
        ".DS_Store",
        "*.min.js",
        "*.min.css",
        "dist",
        "build",
        ".next",
        "target",
        "*.generated.*",
        "*.pb.go",
        "*.pb.swift",
    )

    def validate(self) -> None:
        for entry in self.allowlist:
            entry.validate()
        # Validates mirrors_root is a valid path
        _ = Path(self.mirrors_root).parent if self.mirrors_root else None


def load_config(path: str | Path) -> IndexerConfig:
    """Load config from a JSON file, validate, return IndexerConfig."""
    raw = json.loads(Path(path).read_text())
    entries = tuple(
        AllowlistEntry(
            owner_name=e["owner_name"],
            extra_refs=tuple(e.get("extra_refs", [])),
        )
        for e in raw.get("allowlist", [])
    )
    cfg = IndexerConfig(
        allowlist=entries,
        mirrors_root=raw.get("mirrors_root", IndexerConfig.mirrors_root),
        webhook_secret=raw.get("webhook_secret", ""),
        webhook_port=raw.get("webhook_port", IndexerConfig.webhook_port),
        webhook_rate_limit=raw.get(
            "webhook_rate_limit", IndexerConfig.webhook_rate_limit
        ),
        reconcile_interval_minutes=raw.get(
            "reconcile_interval_minutes",
            IndexerConfig.reconcile_interval_minutes,
        ),
        inactive_days=raw.get(
            "inactive_days", IndexerConfig.inactive_days
        ),
        inactive_pool_gb=raw.get(
            "inactive_pool_gb", IndexerConfig.inactive_pool_gb
        ),
        db_host=raw.get("db_host", IndexerConfig.db_host),
        db_port=raw.get("db_port", IndexerConfig.db_port),
        db_name=raw.get("db_name", IndexerConfig.db_name),
        db_user=raw.get("db_user", IndexerConfig.db_user),
        db_password=raw.get("db_password", ""),
        excluded_paths=tuple(
            raw.get("excluded_paths", list(IndexerConfig.excluded_paths))
        ),
    )
    cfg.validate()
    return cfg


def default_config_path() -> Path:
    """Return the default config file location."""
    return Path("/home/ubuntu/.hermes/indexer/config.json")
