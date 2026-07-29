"""Unit tests for hermes/indexer/sync.py.

Covers tickets #56 (first-index), #57 (incremental sync),
#59 (reconcile), #60 (revoke/purge), and #61 (active-set).

All tests use unittest.mock; no network or Postgres required.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from hermes.indexer.config import IndexerConfig
from hermes.indexer.db import RepoRow, SyncCursorRow
from hermes.indexer.mirror import MirrorState
from hermes.indexer.parser import (
    ExtractedSymbol,
    FileChunk,
    ParsedFile,
)
from hermes.indexer.sync import SyncJob

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(**overrides: object) -> IndexerConfig:
    """Return an IndexerConfig with sensible defaults for unit tests."""
    kwargs: dict[str, object] = {
        "allowlist": (),
        "inactive_days": 14,
        "inactive_pool_gb": 80,
    }
    kwargs.update(overrides)
    return IndexerConfig(**kwargs)  # type: ignore[arg-type]


def _repo_row(
    idx: int = 1,
    owner_name: str = "org/myrepo",
    default_branch: str = "main",
    status: str = "active",
) -> RepoRow:
    return RepoRow(
        id=idx,
        owner_name=owner_name,
        default_branch=default_branch,
        status=status,
        revoked_at=None,
        purge_after=None,
        created_at=datetime.now(timezone.utc),
    )


def _cursor_row(
    repo_id: int = 1,
    ref_name: str = "main",
    after_sha: str = "aaa",
) -> SyncCursorRow:
    return SyncCursorRow(
        id=1,
        repo_id=repo_id,
        ref_name=ref_name,
        last_before_sha=None,
        last_after_sha=after_sha,
        last_success_at=datetime.now(timezone.utc),
    )


def _mirror_state(
    owner_name: str = "org/myrepo",
    clone_mode: str = "full",
    last_activity: datetime | None = None,
    disk_bytes: int | None = 1_000_000,
) -> MirrorState:
    return MirrorState(
        owner_name=owner_name,
        mirror_path=f"/tmp/mirrors/{owner_name}",
        clone_mode=clone_mode,
        default_branch="main",
        pinned_sha=None,
        last_activity=last_activity,
        disk_bytes=disk_bytes,
    )


# ---------------------------------------------------------------------------
# Base test case
# ---------------------------------------------------------------------------


class SyncJobTestCase(unittest.TestCase):
    """Sets up a SyncJob with a mock DB and shared config."""

    def setUp(self) -> None:
        self.config = _config()
        self.mock_db = mock.MagicMock(name="CodebaseIndexDB")
        self.job = SyncJob(self.config, db=self.mock_db)

    def tearDown(self) -> None:
        self.job.close()


# ===========================================================================
# Ticket #56 — first_index
# ===========================================================================


@mock.patch("hermes.indexer.sync.full_clone")
@mock.patch("hermes.indexer.sync.resolve_ref_sha")
@mock.patch("hermes.indexer.sync.list_working_files")
@mock.patch("hermes.indexer.sync.show_file_content")
@mock.patch("hermes.indexer.sync.is_excluded_path")
@mock.patch("hermes.indexer.sync.parse_source")
@mock.patch("hermes.indexer.sync.get_repo_default_branch")
class FirstIndexTests(SyncJobTestCase):
    """SyncJob.first_index — full materialization (ticket #56)."""

    def test_first_index_full_materialization(
        self,
        mock_get_branch: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """first_index calls full_clone, upsert_repo, walks tree,
        parses files, and writes symbols/chunks."""
        mock_get_branch.return_value = "main"
        self.mock_db.upsert_repo.return_value = 42
        mock_resolve.side_effect = ["sha1", "sha2"]

        tree = [
            {"path": "src/lib.py"},
            {"path": "README.md"},
        ]
        mock_list.return_value = tree
        mock_excluded.return_value = False

        parsed = ParsedFile(
            path="src/lib.py",
            language="python",
            content_sha="chksum",
            symbols=(
                ExtractedSymbol("Foo", "class", 1, 10, "class Foo:"),
            ),
            chunks=(
                FileChunk(0, 1, 10, "content", "chk1"),
            ),
        )
        mock_show.return_value = "source code"
        mock_parse.return_value = parsed
        self.mock_db.upsert_file.return_value = 99
        self.mock_db.upsert_ref.return_value = 7

        result = self.job.first_index("org/myrepo")

        # 1. Clone called
        mock_clone.assert_called_once_with("org/myrepo", self.config)
        # 2. Upsert repo
        self.mock_db.upsert_repo.assert_called_once_with(
            "org/myrepo", "main"
        )
        # 3. Create ref row
        self.mock_db.upsert_ref.assert_called_once_with(42, "main", "sha1")
        # 4. Walk tree
        mock_list.assert_called_once_with("org/myrepo", "sha1", self.config)
        # 5. Show + parse every file
        assert mock_show.call_count == 2
        assert mock_parse.call_count == 2
        # 6. Upsert file, insert symbol, insert chunk
        self.mock_db.insert_symbol.assert_called()
        self.assertEqual(self.mock_db.insert_symbol.call_count, 2)
        self.mock_db.insert_chunk.assert_called()
        self.assertEqual(self.mock_db.insert_chunk.call_count, 2)
        # 7. Cursor advanced
        self.mock_db.upsert_cursor.assert_called_once_with(
            repo_id=42,
            ref_name="main",
            before_sha=None,
            after_sha="sha1",
        )

        self.assertEqual(result["owner_name"], "org/myrepo")
        self.assertEqual(result["repo_id"], 42)
        self.assertEqual(result["symbols_count"], 2)
        self.assertEqual(result["chunks_count"], 2)
    def test_first_index_advances_cursor(
        self,
        mock_get_branch: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """first_index advances the sync cursor after success."""
        mock_get_branch.return_value = "main"
        self.mock_db.upsert_repo.return_value = 42
        mock_resolve.return_value = "sha1"
        mock_list.return_value = []
        mock_excluded.return_value = False
        self.mock_db.upsert_ref.return_value = 7

        self.job.first_index("org/myrepo")

        self.mock_db.upsert_cursor.assert_called_once_with(
            repo_id=42,
            ref_name="main",
            before_sha=None,
            after_sha="sha1",
        )

    def test_first_index_excludes_excluded_paths(
        self,
        mock_get_branch: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """first_index skips paths matching exclusion patterns."""
        mock_get_branch.return_value = "main"
        self.mock_db.upsert_repo.return_value = 42
        mock_resolve.side_effect = ["sha1", "sha2"]

        tree = [
            {"path": "src/lib.py"},       # included
            {"path": "node_modules/pkg"},  # excluded
            {"path": "vendor/v.js"},       # excluded
        ]
        mock_list.return_value = tree
        # Return True for excluded paths
        mock_excluded.side_effect = lambda p, _: p in (
            "node_modules/pkg",
            "vendor/v.js",
        )

        parsed = ParsedFile(
            path="src/lib.py",
            language="python",
            content_sha="chk",
        )
        mock_show.return_value = "code"
        mock_parse.return_value = parsed
        self.mock_db.upsert_ref.return_value = 7

        result = self.job.first_index("org/myrepo")

        assert mock_parse.call_count == 1
        assert mock_show.call_count == 1
        self.assertEqual(result["files_count"], 1)
        self.assertEqual(result["excluded_count"], 2)
        self.mock_db.upsert_file.assert_called_once()

    def test_first_index_resolves_default_branch_on_error(
        self,
        mock_get_branch: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """first_index falls back to 'main' when get_repo_default_branch
        raises RuntimeError."""
        mock_get_branch.side_effect = RuntimeError("no remote")
        self.mock_db.upsert_repo.return_value = 42
        mock_resolve.return_value = "sha1"
        mock_list.return_value = []
        mock_excluded.return_value = False
        self.mock_db.upsert_ref.return_value = 7

        result = self.job.first_index("org/myrepo")

        self.mock_db.upsert_repo.assert_called_once_with(
            "org/myrepo", "main"
        )
        self.assertEqual(result["repo_id"], 42)


# ===========================================================================
# Ticket #57 — incremental_sync
# ===========================================================================


@mock.patch("hermes.indexer.sync.full_clone")
@mock.patch("hermes.indexer.sync.resolve_ref_sha")
@mock.patch("hermes.indexer.sync.list_working_files")
@mock.patch("hermes.indexer.sync.show_file_content")
@mock.patch("hermes.indexer.sync.is_excluded_path")
@mock.patch("hermes.indexer.sync.parse_source")
@mock.patch("hermes.indexer.sync.diff_files_between")
class IncrementalSyncTests(SyncJobTestCase):
    """SyncJob.incremental_sync — delta updates (ticket #57)."""

    def test_incremental_sync_no_change(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """Same before_sha and after_sha returns 'no_change'."""
        self.mock_db.get_repo.return_value = _repo_row()
        self.mock_db.upsert_ref.return_value = 1

        result = self.job.incremental_sync(
            "org/myrepo", "main", "abc123", before_sha="abc123"
        )

        self.assertEqual(result["status"], "no_change")
        mock_diff.assert_not_called()
        mock_parse.assert_not_called()
        self.mock_db.upsert_cursor.assert_called_once()

    def test_incremental_sync_calls_diff(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """Different SHAs calls diff_files_between."""
        self.mock_db.get_repo.return_value = _repo_row()
        self.mock_db.upsert_ref.return_value = 1
        mock_diff.return_value = {}  # no file changes
        mock_list.side_effect = [[], []]  # before and after tree
        mock_excluded.return_value = False

        result = self.job.incremental_sync(
            "org/myrepo", "main", "after", before_sha="before"
        )

        mock_diff.assert_called_once_with(
            "org/myrepo", "before", "after", self.config
        )
        self.assertEqual(result["status"], "synced")
        self.assertEqual(result["files_added"], 0)
        self.assertEqual(result["files_modified"], 0)
        self.assertEqual(result["files_deleted"], 0)

    def test_incremental_sync_handles_added_modified_deleted(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """Each diff status leads to correct counters."""
        self.mock_db.get_repo.return_value = _repo_row()
        self.mock_db.upsert_ref.return_value = 1
        mock_diff.return_value = {
            "src/new.py": "added",
            "src/mod.py": "modified",
            "src/old.py": "deleted",
        }
        mock_excluded.return_value = False

        # Two trees for delete_files_not_in logic
        mock_list.side_effect = [
            [
                {"path": "src/new.py"},
                {"path": "src/mod.py"},
                {"path": "src/old.py"},
            ],
            [{"path": "src/new.py"}, {"path": "src/mod.py"}],
        ]

        parsed = ParsedFile(
            path="src/new.py",
            language="python",
            content_sha="c1",
        )
        mock_show.return_value = "code"
        mock_parse.return_value = parsed
        self.mock_db.upsert_file.return_value = 99

        result = self.job.incremental_sync(
            "org/myrepo", "main", "after", before_sha="before"
        )

        self.assertEqual(result["files_added"], 1)
        self.assertEqual(result["files_modified"], 1)
        self.assertEqual(result["files_deleted"], 1)

    def test_incremental_sync_handles_excluded_in_diff(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """Excluded paths are counted as deleted if status is deleted,
        otherwise skipped silently."""
        self.mock_db.get_repo.return_value = _repo_row()
        self.mock_db.upsert_ref.return_value = 1
        mock_diff.return_value = {
            "node_modules/pkg": "deleted",
            "venv/lib": "modified",   # excluded, not added/modified
        }
        mock_excluded.return_value = True
        mock_list.side_effect = [[], []]

        result = self.job.incremental_sync(
            "org/myrepo", "main", "after", before_sha="before"
        )

        # deleted path counted, modified excluded path ignored
        self.assertEqual(result["files_deleted"], 1)
        self.assertEqual(result["files_modified"], 0)
        self.assertEqual(result["files_added"], 0)

    def test_incremental_sync_advances_cursor_on_success(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """Cursor is advanced only after successful sync."""
        self.mock_db.get_repo.return_value = _repo_row()
        self.mock_db.upsert_ref.return_value = 1
        mock_diff.return_value = {}
        mock_list.side_effect = [[], []]
        mock_excluded.return_value = False

        self.job.incremental_sync(
            "org/myrepo", "main", "after", before_sha="before"
        )

        self.mock_db.upsert_cursor.assert_called_once_with(
            repo_id=1,
            ref_name="main",
            before_sha="before",
            after_sha="after",
        )

    def test_incremental_sync_resolves_before_sha_from_cursor(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """When before_sha is None, resolves from cursor."""
        self.mock_db.get_repo.return_value = _repo_row()
        self.mock_db.get_cursor.return_value = _cursor_row(
            after_sha="cursor_sha"
        )
        self.mock_db.upsert_ref.return_value = 1
        mock_diff.return_value = {}
        mock_list.side_effect = [[], []]
        mock_excluded.return_value = False

        result = self.job.incremental_sync(
            "org/myrepo", "main", "after", before_sha=None
        )

        self.mock_db.get_cursor.assert_called_once_with(1, "main")
        mock_diff.assert_called_once_with(
            "org/myrepo", "cursor_sha", "after", self.config
        )
        self.assertEqual(result["status"], "synced")

    def test_incremental_sync_falls_back_to_first_index(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """When repo not found, falls back to first_index."""
        self.mock_db.get_repo.return_value = None
        mock_resolve.return_value = "sha1"
        mock_list.return_value = []
        mock_excluded.return_value = False
        self.mock_db.upsert_repo.return_value = 99
        self.mock_db.upsert_ref.return_value = 7

        result = self.job.incremental_sync("org/myrepo", "main", "after")

        # first_index was called (not incremental)
        self.mock_db.upsert_repo.assert_called_once()
        self.assertIn("repo_id", result)

    def test_incremental_sync_falls_back_when_no_cursor(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """When before_sha is None and no cursor, falls back to
        first_index."""
        self.mock_db.get_repo.return_value = _repo_row()
        self.mock_db.get_cursor.return_value = None
        mock_resolve.return_value = "sha1"
        mock_list.return_value = []
        mock_excluded.return_value = False
        self.mock_db.upsert_repo.return_value = 99
        self.mock_db.upsert_ref.return_value = 7

        result = self.job.incremental_sync(
            "org/myrepo", "main", "after", before_sha=None
        )

        self.mock_db.upsert_repo.assert_called_once()
        self.assertIn("repo_id", result)


# ===========================================================================
# Ticket #59 — reconcile_refs
# ===========================================================================


@mock.patch("hermes.indexer.sync.resolve_ref_sha")
@mock.patch("hermes.indexer.sync.full_clone")
@mock.patch("hermes.indexer.sync.list_working_files")
@mock.patch("hermes.indexer.sync.show_file_content")
@mock.patch("hermes.indexer.sync.is_excluded_path")
@mock.patch("hermes.indexer.sync.parse_source")
@mock.patch("hermes.indexer.sync.diff_files_between")
class ReconcileRefsTests(SyncJobTestCase):
    """SyncJob.reconcile_refs — drift repair (ticket #59)."""

    def test_reconcile_refs_detects_mismatch_and_syncs(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_clone: mock.MagicMock,
        mock_resolve: mock.MagicMock,
    ) -> None:
        """Detects cursor != current SHA and calls incremental_sync."""
        self.mock_db.list_active_repos.return_value = [
            _repo_row(owner_name="org/repo1"),
            _repo_row(idx=2, owner_name="org/repo2"),
        ]
        mock_resolve.return_value = "remote_sha"
        self.mock_db.get_cursor.side_effect = [
            _cursor_row(after_sha="old_sha"),       # repo1: mismatch
            _cursor_row(after_sha="remote_sha"),     # repo2: match
        ]
        mock_diff.return_value = {}
        mock_list.side_effect = [[], []]
        mock_excluded.return_value = False
        self.mock_db.upsert_ref.return_value = 1

        results = self.job.reconcile_refs()

        # repo1 repaired, repo2 skipped
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["owner_name"], "org/repo1")
        self.assertEqual(results[0]["action"], "repaired")
        self.assertEqual(results[0]["from_sha"], "old_sha")
        self.assertEqual(results[0]["to_sha"], "remote_sha")

    def test_reconcile_refs_returns_empty_when_matching(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_clone: mock.MagicMock,
        mock_resolve: mock.MagicMock,
    ) -> None:
        """Returns empty list when cursors match remote SHAs."""
        self.mock_db.list_active_repos.return_value = [
            _repo_row(owner_name="org/repo1"),
        ]
        mock_resolve.return_value = "sha_match"
        self.mock_db.get_cursor.return_value = _cursor_row(
            after_sha="sha_match"
        )

        results = self.job.reconcile_refs()

        self.assertEqual(results, [])

    def test_reconcile_refs_resolves_on_resolve_failure(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_clone: mock.MagicMock,
        mock_resolve: mock.MagicMock,
    ) -> None:
        """When resolve_ref_sha fails, re-clones and retries."""
        self.mock_db.list_active_repos.return_value = [
            _repo_row(owner_name="org/repo1"),
        ]
        # First call fails, second succeeds after clone
        mock_resolve.side_effect = [
            RuntimeError("no ref"),
            "recovered_sha",
        ]
        self.mock_db.get_cursor.return_value = _cursor_row(
            after_sha="old_sha"
        )
        mock_diff.return_value = {}
        mock_list.side_effect = [[], []]
        mock_excluded.return_value = False
        self.mock_db.upsert_ref.return_value = 1

        results = self.job.reconcile_refs()

        # full_clone called by reconcile_refs (after resolve failure)
        # and by incremental_sync (inside the sync path)
        self.assertEqual(mock_clone.call_count, 2)
        mock_clone.assert_any_call("org/repo1", self.config)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "repaired")

    def test_reconcile_refs_skips_on_permanent_failure(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_clone: mock.MagicMock,
        mock_resolve: mock.MagicMock,
    ) -> None:
        """Permanent resolve failure is logged and skipped."""
        self.mock_db.list_active_repos.return_value = [
            _repo_row(owner_name="org/repo1"),
        ]
        mock_resolve.side_effect = RuntimeError("still fails")

        results = self.job.reconcile_refs()

        self.assertEqual(results, [])
        mock_clone.assert_called_once()

    def test_reconcile_refs_no_cursor_triggers_first_index(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_clone: mock.MagicMock,
        mock_resolve: mock.MagicMock,
    ) -> None:
        """No existing cursor triggers sync via incremental_sync
        with before_sha=None (falls through to first_index)."""
        self.mock_db.list_active_repos.return_value = [
            _repo_row(owner_name="org/nocursor"),
        ]
        mock_resolve.return_value = "remote_sha"
        self.mock_db.get_cursor.return_value = None
        self.mock_db.get_repo.return_value = None  # triggers first_index

        # first_index setup
        self.mock_db.upsert_repo.return_value = 99
        mock_list.return_value = []
        mock_excluded.return_value = False
        self.mock_db.upsert_ref.return_value = 7

        results = self.job.reconcile_refs()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "repaired")


# ===========================================================================
# Ticket #60 — revoke / purge
# ===========================================================================


class RevokePurgeTests(SyncJobTestCase):
    """SyncJob revoke, force_purge, resume, purge_expired (ticket #60)."""

    def test_revoke_repo_sets_status_and_purge_after(self) -> None:
        """revoke_repo returns status 'revoked' with a future
        purge_after timestamp."""
        self.mock_db.get_repo.return_value = _repo_row()
        purge_dt = datetime.now(timezone.utc) + timedelta(days=30)
        self.mock_db.revoke_repo.return_value = purge_dt

        result = self.job.revoke_repo("org/myrepo")

        self.assertEqual(result["status"], "revoked")
        self.assertEqual(result["purge_after"], purge_dt.isoformat())
        self.mock_db.revoke_repo.assert_called_once_with("org/myrepo")

    def test_revoke_repo_raises_for_missing_repo(self) -> None:
        """revoke_repo raises ValueError when repo not in catalog."""
        self.mock_db.get_repo.return_value = None

        with self.assertRaises(ValueError):
            self.job.revoke_repo("org/nonexistent")

    @mock.patch("hermes.indexer.sync.remove_mirror")
    def test_force_purge_deletes_repo_and_mirror(
        self,
        mock_remove: mock.MagicMock,
    ) -> None:
        """force_purge calls db.force_purge_repo + remove_mirror."""
        result = self.job.force_purge("org/myrepo")

        self.mock_db.force_purge_repo.assert_called_once_with("org/myrepo")
        mock_remove.assert_called_once_with("org/myrepo", self.config)
        self.assertEqual(result["status"], "purged")

    @mock.patch("hermes.indexer.sync.remove_mirror")
    def test_purge_expired_finds_and_purges(
        self,
        mock_remove: mock.MagicMock,
    ) -> None:
        """purge_expired queries expired repos and force-purges each."""
        mock_conn = mock.MagicMock(name="conn")
        mock_cursor = mock.MagicMock(name="cursor")
        mock_cursor.fetchall.return_value = [
            ("org/expired1",),
            ("org/expired2",),
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        self.mock_db._connect.return_value = mock_conn

        results = self.job.purge_expired()

        self.assertEqual(len(results), 2)
        self.mock_db.force_purge_repo.assert_has_calls(
            [
                mock.call("org/expired1"),
                mock.call("org/expired2"),
            ]
        )
        mock_remove.assert_has_calls(
            [
                mock.call("org/expired1", self.config),
                mock.call("org/expired2", self.config),
            ]
        )

    @mock.patch("hermes.indexer.sync._resolve_default_branch")
    @mock.patch("hermes.indexer.sync.full_clone")
    @mock.patch("hermes.indexer.sync.resolve_ref_sha")
    @mock.patch("hermes.indexer.sync.list_working_files")
    @mock.patch("hermes.indexer.sync.show_file_content")
    @mock.patch("hermes.indexer.sync.is_excluded_path")
    @mock.patch("hermes.indexer.sync.parse_source")
    @mock.patch("hermes.indexer.sync.diff_files_between")
    def test_resume_repo_reactivates_and_syncs(
        self,
        mock_diff: mock.MagicMock,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
        mock_branch: mock.MagicMock,
    ) -> None:
        """resume_repo on a revoked repo re-activates and syncs from
        last SHA."""
        self.mock_db.get_repo.return_value = _repo_row(status="revoked")
        mock_branch.return_value = "main"
        self.mock_db.get_cursor.return_value = _cursor_row(
            after_sha="last_sha"
        )
        mock_diff.return_value = {}
        mock_list.side_effect = [[], []]
        mock_excluded.return_value = False
        self.mock_db.upsert_ref.return_value = 1

        result = self.job.resume_repo("org/myrepo")

        # Resume calls upsert_repo to reactivate
        self.mock_db.upsert_repo.assert_called_once_with(
            "org/myrepo", "main"
        )
        # incremental_sync receives same before/after from cursor → no_change
        # (diff_files_between is not called in the no-change fast path)
        mock_diff.assert_not_called()
        # Cursor was still advanced (upsert_cursor called in no-change path)
        self.mock_db.upsert_cursor.assert_called_once()
        self.assertEqual(result["status"], "no_change")

    @mock.patch("hermes.indexer.sync._resolve_default_branch")
    @mock.patch("hermes.indexer.sync.full_clone")
    @mock.patch("hermes.indexer.sync.resolve_ref_sha")
    @mock.patch("hermes.indexer.sync.list_working_files")
    @mock.patch("hermes.indexer.sync.show_file_content")
    @mock.patch("hermes.indexer.sync.is_excluded_path")
    @mock.patch("hermes.indexer.sync.parse_source")
    def test_resume_repo_does_first_index_when_no_cursor(
        self,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
        mock_branch: mock.MagicMock,
    ) -> None:
        """resume_repo falls back to first_index when no cursor exists."""
        self.mock_db.get_repo.return_value = _repo_row(status="revoked")
        mock_branch.return_value = "main"
        self.mock_db.get_cursor.return_value = None
        mock_resolve.return_value = "sha1"
        mock_list.return_value = []
        mock_excluded.return_value = False
        self.mock_db.upsert_repo.return_value = 42
        self.mock_db.upsert_ref.return_value = 7

        result = self.job.resume_repo("org/myrepo")

        # upsert_repo called by both resume_repo and first_index
        self.mock_db.upsert_repo.assert_any_call("org/myrepo", "main")
        self.assertEqual(self.mock_db.upsert_repo.call_count, 2)
        self.assertIn("repo_id", result)

    @mock.patch("hermes.indexer.sync.full_clone")
    @mock.patch("hermes.indexer.sync.resolve_ref_sha")
    @mock.patch("hermes.indexer.sync.list_working_files")
    @mock.patch("hermes.indexer.sync.show_file_content")
    @mock.patch("hermes.indexer.sync.is_excluded_path")
    @mock.patch("hermes.indexer.sync.parse_source")
    def test_resume_repo_does_first_index_when_missing(
        self,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """resume_repo falls back to first_index when repo not found."""
        self.mock_db.get_repo.return_value = None
        self.mock_db.upsert_repo.return_value = 42
        mock_resolve.return_value = "sha1"
        mock_list.return_value = []
        mock_excluded.return_value = False
        self.mock_db.upsert_ref.return_value = 7

        result = self.job.resume_repo("org/newrepo")

        self.assertIn("repo_id", result)

    @mock.patch("hermes.indexer.sync.full_clone")
    @mock.patch("hermes.indexer.sync.diff_files_between")
    @mock.patch("hermes.indexer.sync.list_working_files")
    @mock.patch("hermes.indexer.sync.show_file_content")
    @mock.patch("hermes.indexer.sync.is_excluded_path")
    @mock.patch("hermes.indexer.sync.parse_source")
    def test_resume_repo_skips_resume_when_already_active(
        self,
        mock_parse: mock.MagicMock,
        mock_excluded: mock.MagicMock,
        mock_show: mock.MagicMock,
        mock_list: mock.MagicMock,
        mock_diff: mock.MagicMock,
        mock_clone: mock.MagicMock,
    ) -> None:
        """resume_repo on an active repo runs incremental_sync from cursor."""
        self.mock_db.get_repo.return_value = _repo_row(status="active")
        self.mock_db.get_cursor.return_value = _cursor_row(
            after_sha="last_sha"
        )
        mock_diff.return_value = {}
        mock_list.side_effect = [[], []]
        mock_excluded.return_value = False
        self.mock_db.upsert_ref.return_value = 1

        result = self.job.resume_repo("org/myrepo")

        # No upsert_repo call (was not revoked)
        self.mock_db.upsert_repo.assert_not_called()
        # Same before/after SHA from cursor → no_change fast path
        mock_diff.assert_not_called()
        self.assertEqual(result["status"], "no_change")


# ===========================================================================
# Ticket #61 — active-set management
# ===========================================================================


@mock.patch("hermes.indexer.sync.get_mirror_state")
class DemoteInactiveTests(SyncJobTestCase):
    """SyncJob.demote_inactive (ticket #61)."""

    def test_demote_inactive_skips_active(
        self,
        mock_state: mock.MagicMock,
    ) -> None:
        """Active repos (idle < inactive_days) are skipped."""
        days_ago = datetime.now(timezone.utc) - timedelta(days=5)
        self.mock_db.list_active_repos.return_value = [
            _repo_row(owner_name="org/active1"),
        ]
        mock_state.return_value = _mirror_state(last_activity=days_ago)

        results = self.job.demote_inactive()

        self.assertEqual(results, [])

    @mock.patch("hermes.indexer.sync.demote_to_sparse")
    def test_demote_inactive_demotes_idle(
        self,
        mock_demote: mock.MagicMock,
        mock_state: mock.MagicMock,
    ) -> None:
        """Repos idle past inactive_days are demoted."""
        old = datetime.now(timezone.utc) - timedelta(days=20)
        self.mock_db.list_active_repos.return_value = [
            _repo_row(owner_name="org/idle1"),
            _repo_row(idx=2, owner_name="org/idle2"),
        ]
        mock_state.return_value = _mirror_state(last_activity=old)

        results = self.job.demote_inactive()

        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["action"], "demoted")
            self.assertGreaterEqual(r["idle_days"], 14)
        mock_demote.assert_has_calls(
            [
                mock.call("org/idle1", self.config),
                mock.call("org/idle2", self.config),
            ]
        )

    def test_demote_inactive_skips_none_state(
        self,
        mock_state: mock.MagicMock,
    ) -> None:
        """Repos with no mirror state are skipped."""
        self.mock_db.list_active_repos.return_value = [
            _repo_row(owner_name="org/nostate"),
        ]
        mock_state.return_value = None

        results = self.job.demote_inactive()

        self.assertEqual(results, [])

    def test_demote_inactive_skips_none_activity(
        self,
        mock_state: mock.MagicMock,
    ) -> None:
        """Repos with no last_activity timestamp are skipped."""
        self.mock_db.list_active_repos.return_value = [
            _repo_row(owner_name="org/noactivity"),
        ]
        mock_state.return_value = _mirror_state(last_activity=None)

        results = self.job.demote_inactive()

        self.assertEqual(results, [])


class CheckInactivePoolSizeTests(SyncJobTestCase):
    """SyncJob.check_inactive_pool_size (ticket #61)."""

    @mock.patch("hermes.indexer.sync.get_mirror_state")
    def test_pool_size_within_capacity(
        self,
        mock_state: mock.MagicMock,
    ) -> None:
        """Pool under 90% threshold reports warning=False."""
        self.mock_db.list_active_repos.return_value = [
            _repo_row(owner_name="org/sparse1"),
        ]
        # 40 GB used (cap is 80, 90% = 72)
        bytes_40gb = 40 * 1024**3
        mock_state.return_value = _mirror_state(
            clone_mode="sparse",
            disk_bytes=bytes_40gb,
        )

        result = self.job.check_inactive_pool_size()

        self.assertEqual(result["cap_gb"], 80)
        self.assertAlmostEqual(result["used_gb"], 40.0, delta=1.0)
        self.assertFalse(result["warning"])

    @mock.patch("hermes.indexer.sync.get_mirror_state")
    def test_pool_size_triggers_warning_at_90_percent(
        self,
        mock_state: mock.MagicMock,
    ) -> None:
        """Pool at 90%+ threshold reports warning=True."""
        self.mock_db.list_active_repos.return_value = [
            _repo_row(owner_name="org/full1"),
        ]
        # 75 GB used (80*0.9 = 72)
        bytes_75gb = 75 * 1024**3
        mock_state.return_value = _mirror_state(
            clone_mode="sparse",
            disk_bytes=bytes_75gb,
        )

        result = self.job.check_inactive_pool_size()

        self.assertTrue(result["warning"])
        self.assertAlmostEqual(result["used_gb"], 75.0, delta=1.0)

    @mock.patch("hermes.indexer.sync.get_mirror_state")
    def test_pool_size_skips_full_clone_repos(
        self,
        mock_state: mock.MagicMock,
    ) -> None:
        """Only repos with non-'full' clone_mode count toward pool."""
        self.mock_db.list_active_repos.return_value = [
            _repo_row(owner_name="org/fullclone"),
            _repo_row(idx=2, owner_name="org/sparse"),
        ]
        mock_state.side_effect = [
            _mirror_state(clone_mode="full", disk_bytes=999_999_999_999),
            _mirror_state(clone_mode="sparse", disk_bytes=1_000_000),
        ]

        result = self.job.check_inactive_pool_size()

        # Only sparse repo counted
        self.assertEqual(len(result["repos"]), 1)
        self.assertEqual(
            result["repos"][0]["owner_name"], "org/sparse"
        )

    @mock.patch("hermes.indexer.sync.get_mirror_state")
    def test_pool_size_handles_none_state(
        self,
        mock_state: mock.MagicMock,
    ) -> None:
        """Repos with no mirror state are skipped."""
        self.mock_db.list_active_repos.return_value = [
            _repo_row(owner_name="org/nostate"),
        ]
        mock_state.return_value = None

        result = self.job.check_inactive_pool_size()

        self.assertEqual(result["total_bytes"], 0)
        self.assertEqual(result["used_gb"], 0.0)
        self.assertEqual(result["repos"], [])

    @mock.patch("hermes.indexer.sync.get_mirror_state")
    def test_pool_size_empty_pool(
        self,
        mock_state: mock.MagicMock,
    ) -> None:
        """Empty active set returns zero pool size."""
        self.mock_db.list_active_repos.return_value = []

        result = self.job.check_inactive_pool_size()

        self.assertEqual(result["total_bytes"], 0)
        self.assertEqual(result["used_gb"], 0.0)
        self.assertFalse(result["warning"])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
