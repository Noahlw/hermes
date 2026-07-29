"""Tests for the Hermes indexer configuration module.

Exercises :mod:`hermes.indexer.config` (AllowlistEntry, IndexerConfig,
and load_config).  Pure unit tests — no Postgres, no network, no
real filesystem I/O (JSON reads are faked via ``unittest.mock``).
"""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from hermes.indexer import utils as indexer_utils
from hermes.indexer.config import AllowlistEntry, IndexerConfig, load_config

# ---------------------------------------------------------------------------
# AllowlistEntry — validation
# ---------------------------------------------------------------------------

class AllowlistEntryValidationTests(unittest.TestCase):
    """AllowlistEntry.validate rejects bad owner_name formats."""

    def test_valid_owner_name_standard(self) -> None:
        """owner/name passes validation."""
        entry = AllowlistEntry(owner_name="org/repo")
        entry.validate()

    def test_valid_owner_name_with_extra_refs(self) -> None:
        """Extra refs are accepted alongside a valid owner/name."""
        entry = AllowlistEntry(
            owner_name="owner/project",
            extra_refs=("refs/heads/main", "refs/tags/v1.0"),
        )
        entry.validate()

    def test_valid_owner_name_hyphens_and_dots(self) -> None:
        """Owner/name with hyphens and dots is valid."""
        entry = AllowlistEntry(owner_name="my-org/my.repo")
        entry.validate()

    def test_invalid_no_slash(self) -> None:
        """A single segment without '/' raises ValueError."""
        entry = AllowlistEntry(owner_name="justrepo")
        with self.assertRaises(ValueError) as ctx:
            entry.validate()
        self.assertIn(
            "owner_name must be 'owner/name'", str(ctx.exception)
        )

    def test_invalid_empty_owner(self) -> None:
        """Empty owner part ('/repo') raises ValueError."""
        entry = AllowlistEntry(owner_name="/repo")
        with self.assertRaises(ValueError) as ctx:
            entry.validate()
        self.assertIn(
            "parts must be non-empty", str(ctx.exception)
        )

    def test_invalid_empty_name(self) -> None:
        """Empty name part ('owner/') raises ValueError."""
        entry = AllowlistEntry(owner_name="owner/")
        with self.assertRaises(ValueError) as ctx:
            entry.validate()
        self.assertIn(
            "parts must be non-empty", str(ctx.exception)
        )

    def test_invalid_too_many_slashes(self) -> None:
        """More than one slash raises ValueError."""
        entry = AllowlistEntry(owner_name="a/b/c")
        with self.assertRaises(ValueError) as ctx:
            entry.validate()
        self.assertIn(
            "owner_name must be 'owner/name'", str(ctx.exception)
        )

    def test_invalid_empty_string(self) -> None:
        """Empty string raises ValueError."""
        entry = AllowlistEntry(owner_name="")
        with self.assertRaises(ValueError):
            entry.validate()


# ---------------------------------------------------------------------------
# IndexerConfig — construction and validation
# ---------------------------------------------------------------------------

class IndexerConfigConstructionTests(unittest.TestCase):
    """IndexerConfig dataclass defaults and basic validation."""

    def test_default_construction(self) -> None:
        """An empty allowlist and all defaults is valid."""
        cfg = IndexerConfig(allowlist=())
        cfg.validate()
        self.assertEqual(cfg.allowlist, ())

    def test_default_values(self) -> None:
        """Default field values match expectations."""
        cfg = IndexerConfig(allowlist=())
        self.assertEqual(
            cfg.mirrors_root, "/home/ubuntu/.hermes/mirrors"
        )
        self.assertEqual(cfg.webhook_secret, "")
        self.assertEqual(cfg.webhook_port, 8080)
        self.assertEqual(cfg.webhook_rate_limit, 60)
        self.assertEqual(cfg.reconcile_interval_minutes, 60)
        self.assertEqual(cfg.inactive_days, 14)
        self.assertEqual(cfg.inactive_pool_gb, 80)
        self.assertEqual(cfg.db_host, "127.0.0.1")
        self.assertEqual(cfg.db_port, 5433)
        self.assertEqual(cfg.db_name, "codebase_index")
        self.assertEqual(cfg.db_user, "postgres")
        self.assertEqual(cfg.db_password, "")

    def test_default_excluded_paths(self) -> None:
        """Default excluded_paths tuple is populated."""
        cfg = IndexerConfig(allowlist=())
        self.assertIsInstance(cfg.excluded_paths, tuple)
        self.assertTrue(len(cfg.excluded_paths) > 0)
        self.assertIn(".git", cfg.excluded_paths)
        self.assertIn("node_modules", cfg.excluded_paths)

    def test_allowlist_bad_entry_rejected_on_validate(self) -> None:
        """validate() calls validate on every allowlist entry."""
        bad = AllowlistEntry(owner_name="badformat")
        cfg = IndexerConfig(allowlist=(bad,))
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_allowlist_with_valid_entries_validates(self) -> None:
        """Config with valid allowlist entries is valid."""
        entry = AllowlistEntry(
            owner_name="org/valid-repo", extra_refs=("main",)
        )
        cfg = IndexerConfig(allowlist=(entry,))
        cfg.validate()

    def test_custom_excluded_paths_valid(self) -> None:
        """Custom excluded_paths does not break validation."""
        cfg = IndexerConfig(
            allowlist=(), excluded_paths=("*.tmp",)
        )
        cfg.validate()

    def test_frozen_dataclass(self) -> None:
        """IndexerConfig is frozen — mutation raises FrozenInstanceError."""
        cfg = IndexerConfig(allowlist=())
        with self.assertRaises(FrozenInstanceError):
            cfg.mirrors_root = "/different"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# load_config — JSON deserialisation and on-read validation
# ---------------------------------------------------------------------------

class LoadConfigTests(unittest.TestCase):
    """load_config reads a JSON file, validates, returns an IndexerConfig."""

    def test_minimal_json(self) -> None:
        """A JSON with only allowlist loads with defaults."""
        payload = {"allowlist": []}
        with patch.object(
            Path, "read_text", return_value=json.dumps(payload)
        ):
            cfg = load_config("/fake/path.json")
        self.assertEqual(cfg.allowlist, ())
        self.assertEqual(cfg.webhook_port, 8080)

    def test_all_fields(self) -> None:
        """Every config field round-trips correctly."""
        payload = {
            "allowlist": [
                {"owner_name": "org/alpha", "extra_refs": ["main"]},
                {"owner_name": "org/beta"},
            ],
            "mirrors_root": "/data/mirrors",
            "webhook_secret": "s3cr3t",
            "webhook_port": 9090,
            "webhook_rate_limit": 120,
            "reconcile_interval_minutes": 30,
            "inactive_days": 7,
            "inactive_pool_gb": 50,
            "db_host": "10.0.0.1",
            "db_port": 6543,
            "db_name": "my_index",
            "db_user": "admin",
            "db_password": "pass123",
            "excluded_paths": ["*.log", "tmp"],
        }
        with patch.object(
            Path, "read_text", return_value=json.dumps(payload)
        ):
            cfg = load_config("/fake/path.json")

        self.assertEqual(len(cfg.allowlist), 2)
        self.assertEqual(cfg.allowlist[0].owner_name, "org/alpha")
        self.assertEqual(cfg.allowlist[0].extra_refs, ("main",))
        self.assertEqual(cfg.allowlist[1].owner_name, "org/beta")
        self.assertEqual(cfg.allowlist[1].extra_refs, ())
        self.assertEqual(cfg.mirrors_root, "/data/mirrors")
        self.assertEqual(cfg.webhook_secret, "s3cr3t")
        self.assertEqual(cfg.webhook_port, 9090)
        self.assertEqual(cfg.webhook_rate_limit, 120)
        self.assertEqual(cfg.reconcile_interval_minutes, 30)
        self.assertEqual(cfg.inactive_days, 7)
        self.assertEqual(cfg.inactive_pool_gb, 50)
        self.assertEqual(cfg.db_host, "10.0.0.1")
        self.assertEqual(cfg.db_port, 6543)
        self.assertEqual(cfg.db_name, "my_index")
        self.assertEqual(cfg.db_user, "admin")
        self.assertEqual(cfg.db_password, "pass123")
        self.assertEqual(cfg.excluded_paths, ("*.log", "tmp"))

    def test_partial_fields_default(self) -> None:
        """Omitted fields fall back to IndexerConfig defaults."""
        payload = {"allowlist": [{"owner_name": "o/r"}]}
        defaults = IndexerConfig(allowlist=())
        with patch.object(
            Path, "read_text", return_value=json.dumps(payload)
        ):
            cfg = load_config("/fake/path.json")

        self.assertEqual(cfg.webhook_port, defaults.webhook_port)
        self.assertEqual(cfg.mirrors_root, defaults.mirrors_root)
        self.assertEqual(cfg.db_host, defaults.db_host)
        self.assertEqual(cfg.db_host, "127.0.0.1")

    def test_load_validates_on_read_bad_slash(self) -> None:
        """load_config calls validate, which rejects invalid data."""
        payload = {"allowlist": [{"owner_name": "no-slash"}]}
        with patch.object(
            Path, "read_text", return_value=json.dumps(payload)
        ), self.assertRaises(ValueError):
            load_config("/fake/path.json")

    def test_load_validates_empty_owner(self) -> None:
        """Invalid allowlist entry in JSON raises during load."""
        payload = {"allowlist": [{"owner_name": "/empty-owner"}]}
        with patch.object(
            Path, "read_text", return_value=json.dumps(payload)
        ), self.assertRaises(ValueError):
            load_config("/fake/path.json")

    def test_extra_refs_defaults_to_empty(self) -> None:
        """An allowlist entry without extra_refs gets an empty tuple."""
        payload = {"allowlist": [{"owner_name": "org/repo"}]}
        with patch.object(
            Path, "read_text", return_value=json.dumps(payload)
        ):
            cfg = load_config("/fake/path.json")
        self.assertEqual(cfg.allowlist[0].extra_refs, ())

    def test_webhook_secret_defaults_empty(self) -> None:
        """Omitted webhook_secret defaults to empty string."""
        payload = {"allowlist": []}
        with patch.object(
            Path, "read_text", return_value=json.dumps(payload)
        ):
            cfg = load_config("/fake/path.json")
        self.assertEqual(cfg.webhook_secret, "")

    def test_db_password_defaults_empty(self) -> None:
        """Omitted db_password defaults to empty string."""
        payload = {"allowlist": []}
        with patch.object(
            Path, "read_text", return_value=json.dumps(payload)
        ):
            cfg = load_config("/fake/path.json")
        self.assertEqual(cfg.db_password, "")

    def test_excluded_paths_default_when_omitted(self) -> None:
        """Omitted excluded_paths falls back to the class default."""
        payload = {"allowlist": []}
        with patch.object(
            Path, "read_text", return_value=json.dumps(payload)
        ):
            cfg = load_config("/fake/path.json")
        self.assertEqual(
            cfg.excluded_paths, IndexerConfig.excluded_paths
        )


# ---------------------------------------------------------------------------
# excluded_paths — pattern compilation
# ---------------------------------------------------------------------------

class ExcludedPathsCompilationTests(unittest.TestCase):
    """_compile_excludes produces compiled regex patterns that correctly
    match or reject paths.

    Each test clears the module-level _EXCLUDE_PATTERNS cache so that
    is_excluded_path recompiles from the config supplied to it.
    """

    def setUp(self) -> None:
        indexer_utils._EXCLUDE_PATTERNS.clear()

    def _check_match(
        self, pattern: str, path: str, should_match: bool
    ) -> None:
        cfg = IndexerConfig(
            allowlist=(), excluded_paths=(pattern,)
        )
        self.assertEqual(
            indexer_utils.is_excluded_path(path, cfg),
            should_match,
            (
                f"pattern={pattern!r} on path={path!r}"
                f" expected excluded={should_match}"
            ),
        )

    # --- Anchor behaviour: pattern matches exact filename or last
    #     path component because regex is (^|/)PATTERN$.

    def test_match_plain_filename(self) -> None:
        """Exact filenames match."""
        self._check_match(".env", ".env", True)

    def test_match_as_last_component(self) -> None:
        """Pattern matches as trailing path component."""
        self._check_match(".env", "some/deep/.env", True)

    def test_reject_similar_name(self) -> None:
        """Anchored pattern does NOT match a longer name."""
        self._check_match(".env", ".envx", False)

    def test_match_pycache_as_last_component(self) -> None:
        """__pycache__ as leaf directory is excluded."""
        self._check_match("__pycache__", "src/__pycache__", True)

    def test_match_git_as_last_component(self) -> None:
        """.git as leaf directory is excluded."""
        self._check_match(".git", "repo/.git", True)

    def test_reject_git_when_not_leaf(self) -> None:
        """.git in mid-path is NOT excluded (anchored at end)."""
        self._check_match(".git", "repo/.git/HEAD", False)

    def test_reject_node_modules_when_not_leaf(self) -> None:
        """node_modules in mid-path is NOT excluded (anchored at end)."""
        self._check_match(
            "node_modules", "a/node_modules/pkg/index.js", False
        )

    def test_match_glob_star(self) -> None:
        """Glob '*' wildcard matches any characters."""
        self._check_match("*.pyc", "lib/foo.pyc", True)

    def test_reject_partial_suffix(self) -> None:
        """Anchored *.pyc does not match a .py file."""
        self._check_match("*.pyc", "foo.py", False)

    def test_match_generated(self) -> None:
        """*.generated.* matches generated files at any depth."""
        self._check_match(
            "*.generated.*", "src/model.generated.ts", True
        )

    def test_match_dot_env_star(self) -> None:
        """.env.* pattern matches .env.local etc."""
        self._check_match(".env.*", ".env.local", True)

    def test_match_min_js(self) -> None:
        """*.min.js matches minified JS files."""
        self._check_match("*.min.js", "dist/app.min.js", True)

    def test_reject_plain_js(self) -> None:
        """*.min.js does not match plain .js."""
        self._check_match("*.min.js", "app.js", False)

    def test_match_glob_question(self) -> None:
        """Glob '?' matches exactly one character."""
        self._check_match("file?.txt", "file1.txt", True)

    def test_glob_question_reject_empty(self) -> None:
        """Glob '?' does NOT match zero characters."""
        self._check_match("file?.txt", "file.txt", False)

    def test_match_vendor_leaf(self) -> None:
        """vendor as leaf directory is excluded."""
        self._check_match("vendor", "vendor", True)

    def test_match_dist_leaf(self) -> None:
        """dist as leaf directory is excluded."""
        self._check_match("dist", "dist", True)

    def test_reject_dist_midpath(self) -> None:
        """dist in mid-path is NOT excluded."""
        self._check_match("dist", "dist/bundle.js", False)

    def test_match_build_leaf(self) -> None:
        """build as leaf directory is excluded."""
        self._check_match("build", "build", True)

    def test_reject_build_midpath(self) -> None:
        """build in mid-path is NOT excluded."""
        self._check_match("build", "build/output.o", False)

    def test_match_ds_store(self) -> None:
        """.DS_Store as leaf is excluded."""
        self._check_match(".DS_Store", ".DS_Store", True)

    def test_multiple_patterns_any_match(self) -> None:
        """Multiple patterns: if any matches at leaf, path is excluded."""
        cfg = IndexerConfig(
            allowlist=(),
            excluded_paths=("*.log", "*.tmp", ".cache"),
        )
        self.assertTrue(
            indexer_utils.is_excluded_path("build.log", cfg)
        )
        self.assertTrue(
            indexer_utils.is_excluded_path("temp.tmp", cfg)
        )
        self.assertTrue(
            indexer_utils.is_excluded_path("vendor/.cache", cfg)
        )
        self.assertFalse(
            indexer_utils.is_excluded_path("src/main.py", cfg)
        )

    def test_pb_go(self) -> None:
        """*.pb.go matches protobuf Go files."""
        self._check_match("*.pb.go", "api.pb.go", True)

    def test_pb_swift(self) -> None:
        """*.pb.swift matches protobuf Swift files."""
        self._check_match("*.pb.swift", "api.pb.swift", True)

    def test_next(self) -> None:
        """.next as leaf directory is excluded."""
        self._check_match(".next", ".next", True)

    def test_target_leaf(self) -> None:
        """target as leaf directory (exact match) is excluded."""
        self._check_match("target", "target", True)

    def test_default_patterns_coverage(self) -> None:
        """The default excluded_paths reject realistic artifacts
        and keep source files."""
        cfg = IndexerConfig(allowlist=())
        cases = [
            # --- files excluded by exact basename match ---
            (".env", True),
            (".DS_Store", True),
            # --- files excluded by glob (*.pyc, *.min.*, *.generated.*,
            #     *.pb.go, *.pb.swift, .env.*) ---
            ("src/foo.pyc", True),
            ("lib/bar.min.js", True),
            ("lib/baz.min.css", True),
            ("src/model.generated.ts", True),
            ("src/api.pb.go", True),
            ("src/api.pb.swift", True),
            (".env.local", True),
            # --- leaf directories excluded ---
            ("node_modules", True),
            ("vendor", True),
            (".git", True),
            ("dist", True),
            ("build", True),
            ("__pycache__", True),
            (".next", True),
            ("target", True),
            # --- non-leaf directories NOT excluded (anchor behaviour) ---
            ("node_modules/lodash/index.js", False),
            ("vendor/some-lib/lib.a", False),
            (".git/HEAD", False),
            ("dist/bundle.js", False),
            ("build/out.o", False),
            ("src/__pycache__/bar.pyc", True),
            # --- source / doc files NOT excluded ---
            ("src/main.py", False),
            ("README.md", False),
            ("src/app.ts", False),
            ("requirements.txt", False),
        ]
        for path_str, expected in cases:
            self.assertEqual(
                indexer_utils.is_excluded_path(path_str, cfg),
                expected,
                f"Mismatch for {path_str!r}: expected excluded={expected}",
            )


if __name__ == "__main__":
    unittest.main()
