from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from hermes.indexer.config import IndexerConfig
from hermes.indexer.db import CodebaseIndexDB
from hermes.indexer.mirror import (
    demote_to_sparse,
    diff_files_between,
    full_clone,
    get_mirror_state,
    get_repo_default_branch,
    list_working_files,
    remove_mirror,
    resolve_ref_sha,
    show_file_content,
)
from hermes.indexer.parser import parse_source
from hermes.indexer.utils import is_excluded_path

log = logging.getLogger(__name__)


class SyncJob:
    """Orchestrates first-index and incremental sync for the codebase indexer.

    Ticket #56: First-index materialization -> knowledge layer.
    Ticket #57: Incremental updates on SHA change.
    """

    def __init__(
        self,
        config: IndexerConfig,
        db: CodebaseIndexDB | None = None,
    ) -> None:
        self._config = config
        self._db = db or CodebaseIndexDB(config)

    def close(self) -> None:
        self._db.close()

    # --- First-index (#56) ---

    def first_index(
        self,
        owner_name: str,
        extra_refs: Sequence[str] = (),
    ) -> dict:
        """Perform first-index full materialization for an allowlisted repo.

        Steps:
        1. Clone full mirror
        2. Upsert repo catalog row
        3. Resolve default branch SHA
        4. Create ref row(s)
        5. Walk tree, parse, write knowledge layer
        6. Advance sync cursor only on success

        Returns summary dict with counts.
        """
        log.info("First-index %s", owner_name)

        # 1. Ensure mirror
        full_clone(owner_name, self._config)

        # 2. Upsert repo
        default_branch = _resolve_default_branch(
            owner_name, self._config
        )
        repo_id = self._db.upsert_repo(owner_name, default_branch)

        # 3. Resolve default SHA
        try:
            default_sha = resolve_ref_sha(
                owner_name,
                f"refs/remotes/origin/{default_branch}",
                self._config,
            )
        except RuntimeError:
            default_sha = resolve_ref_sha(
                owner_name, default_branch, self._config
            )

        # 4. Create ref row for default branch
        refs_to_index = [(default_branch, default_sha)]
        for extra in extra_refs:
            if extra == default_branch:
                continue
            try:
                sha = resolve_ref_sha(
                    owner_name,
                    f"refs/remotes/origin/{extra}",
                    self._config,
                )
                refs_to_index.append((extra, sha))
            except RuntimeError:
                log.warning("Skipping unresolved ref %s for %s", extra, owner_name)
                continue

        total_files = 0
        total_symbols = 0
        total_chunks = 0
        total_excluded = 0

        for ref_name, sha in refs_to_index:
            ref_id = self._db.upsert_ref(repo_id, ref_name, sha)

            # 5. Walk tree at this SHA
            tree = list_working_files(owner_name, sha, self._config)
            for entry in tree:
                rel_path = entry["path"]
                if is_excluded_path(rel_path, self._config):
                    total_excluded += 1
                    continue

                try:
                    content = show_file_content(
                        owner_name, sha, rel_path, self._config
                    )
                except RuntimeError:
                    log.warning(
                        "Skipping unreadable %s @ %s", rel_path, sha
                    )
                    continue

                parsed = parse_source(content, rel_path)

                file_id = self._db.upsert_file(
                    repo_id=repo_id,
                    ref_id=ref_id,
                    path=parsed.path,
                    language=parsed.language,
                    content_sha=parsed.content_sha,
                    commit_sha=sha,
                )
                total_files += 1

                for sym in parsed.symbols:
                    self._db.insert_symbol(
                        file_id=file_id,
                        name=sym.name,
                        kind=sym.kind,
                        start_line=sym.start_line,
                        end_line=sym.end_line,
                        signature=sym.signature,
                    )
                    total_symbols += 1

                for chk in parsed.chunks:
                    self._db.insert_chunk(
                        file_id=file_id,
                        chunk_index=chk.chunk_index,
                        start_line=chk.start_line,
                        end_line=chk.end_line,
                        content=chk.content,
                        content_sha=chk.content_sha,
                    )
                    total_chunks += 1

            # 6. Advance cursor only on full success
            self._db.upsert_cursor(
                repo_id=repo_id,
                ref_name=ref_name,
                before_sha=None,
                after_sha=sha,
            )

        return {
            "owner_name": owner_name,
            "repo_id": repo_id,
            "refs_count": len(refs_to_index),
            "files_count": total_files,
            "symbols_count": total_symbols,
            "chunks_count": total_chunks,
            "excluded_count": total_excluded,
        }

    # --- Incremental sync (#57) ---

    def incremental_sync(
        self,
        owner_name: str,
        ref_name: str,
        after_sha: str,
        before_sha: str | None = None,
    ) -> dict:
        """Perform an incremental sync from before_sha to after_sha.

        If before_sha is None, resolves from cursor or performs a first-index.
        """
        log.info(
            "Incremental sync %s %s: %s -> %s",
            owner_name,
            ref_name,
            before_sha or "(cursor)",
            after_sha,
        )

        repo = self._db.get_repo(owner_name)
        if repo is None:
            # Not indexed yet - do first-index
            return self.first_index(owner_name)

        # Resolve before_sha from cursor if needed
        if before_sha is None:
            cursor = self._db.get_cursor(repo.id, ref_name)
            if cursor and cursor.last_after_sha:
                before_sha = cursor.last_after_sha
            else:
                # No prior state - do first-index
                return self.first_index(owner_name)

        # Ensure mirror is available
        full_clone(owner_name, self._config)

        ref_id = self._db.upsert_ref(repo.id, ref_name, after_sha)

        if before_sha == after_sha:
            # No change
            self._db.upsert_cursor(
                repo_id=repo.id,
                ref_name=ref_name,
                before_sha=before_sha,
                after_sha=after_sha,
            )
            return {
                "owner_name": owner_name,
                "repo_id": repo.id,
                "status": "no_change",
                "files_added": 0,
                "files_modified": 0,
                "files_deleted": 0,
            }

        # Compare the two SHAs
        diff = diff_files_between(
            owner_name, before_sha, after_sha, self._config
        )

        added = 0
        modified = 0
        deleted_count = 0
        total_symbols = 0
        total_chunks = 0

        for path, status in diff.items():
            if is_excluded_path(path, self._config):
                if status == "deleted":
                    deleted_count += 1
                continue

            if status == "deleted":
                # Path no longer in after_sha
                deleted_count += 1
            elif status in ("added", "modified", "renamed"):
                try:
                    content = show_file_content(
                        owner_name, after_sha, path, self._config
                    )
                except RuntimeError:
                    log.warning(
                        "Skipping unreadable %s @ %s", path, after_sha
                    )
                    continue

                parsed = parse_source(content, path)

                file_id = self._db.upsert_file(
                    repo_id=repo.id,
                    ref_id=ref_id,
                    path=parsed.path,
                    language=parsed.language,
                    content_sha=parsed.content_sha,
                    commit_sha=after_sha,
                )

                # Delete old symbols for this path at old SHA so our
                # insert-only symbol table doesn't accumulate orphans.
                self._db.delete_symbols_for_path(
                    repo.id, path, before_sha
                )

                for sym in parsed.symbols:
                    self._db.insert_symbol(
                        file_id=file_id,
                        name=sym.name,
                        kind=sym.kind,
                        start_line=sym.start_line,
                        end_line=sym.end_line,
                        signature=sym.signature,
                    )
                    total_symbols += 1

                for chk in parsed.chunks:
                    self._db.insert_chunk(
                        file_id=file_id,
                        chunk_index=chk.chunk_index,
                        start_line=chk.start_line,
                        end_line=chk.end_line,
                        content=chk.content,
                        content_sha=chk.content_sha,
                    )
                    total_chunks += 1

                if status in ("added", "renamed"):
                    added += 1
                else:
                    modified += 1

        # Remove files that exist in before but not after
        kept_paths = set()
        before_tree = list_working_files(
            owner_name, before_sha, self._config
        )
        after_tree = list_working_files(
            owner_name, after_sha, self._config
        )
        after_paths = {e["path"] for e in after_tree}
        for entry in before_tree:
            if entry["path"] not in after_paths:
                # This file was deleted - will be cleaned by
                # delete_files_not_in below
                pass
        kept_paths = after_paths
        self._db.delete_files_not_in(
            repo.id, after_sha, kept_paths
        )

        # Advance cursor only on full success
        self._db.upsert_cursor(
            repo_id=repo.id,
            ref_name=ref_name,
            before_sha=before_sha,
            after_sha=after_sha,
        )

        return {
            "owner_name": owner_name,
            "repo_id": repo.id,
            "status": "synced",
            "before_sha": before_sha,
            "after_sha": after_sha,
            "files_added": added,
            "files_modified": modified,
            "files_deleted": deleted_count,
            "symbols_written": total_symbols,
            "chunks_written": total_chunks,
        }

    # --- Revoke/purge (#60) ---

    def revoke_repo(self, owner_name: str) -> dict:
        """Remove a repo from the allowlist (soft-delete).

        Marks status 'revoked' with 30-day grace.
        """
        repo = self._db.get_repo(owner_name)
        if repo is None:
            raise ValueError(f"Repo {owner_name} not in catalog")

        purge_after = self._db.revoke_repo(owner_name)
        return {
            "owner_name": owner_name,
            "status": "revoked",
            "purge_after": purge_after.isoformat(),
        }

    def force_purge(self, owner_name: str) -> dict:
        """Immediately remove a repo from knowledge layer and disk."""
        log.info("Force-purging %s", owner_name)
        self._db.force_purge_repo(owner_name)
        remove_mirror(owner_name, self._config)
        return {
            "owner_name": owner_name,
            "status": "purged",
        }

    def purge_expired(self) -> list[dict]:
        """Purge all repos whose purge_after has passed."""
        conn = self._db._connect()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT owner_name FROM repos
                   WHERE status = 'revoked'
                     AND purge_after IS NOT NULL
                     AND purge_after <= NOW()"""
            )
            expired = [r[0] for r in cur.fetchall()]

        results = []
        for name in expired:
            results.append(self.force_purge(name))
        return results

    def resume_repo(self, owner_name: str) -> dict:
        """Re-add a repo during grace period, resume from last SHA."""
        repo = self._db.get_repo(owner_name)
        if repo is None:
            # New repo - do first-index
            return self.first_index(owner_name)
        if repo.status != "revoked":
            # Already active - incremental sync is fine
            cursor = self._db.get_cursor(
                repo.id, repo.default_branch
            )
            if cursor and cursor.last_after_sha:
                return self.incremental_sync(
                    owner_name,
                    repo.default_branch,
                    cursor.last_after_sha,
                )
            return self.first_index(owner_name)

        # Reactivate
        default_branch = _resolve_default_branch(
            owner_name, self._config
        )
        self._db.upsert_repo(owner_name, default_branch)

        # Try to resume from last SHA
        cursor = self._db.get_cursor(repo.id, repo.default_branch)
        if cursor and cursor.last_after_sha:
            return self.incremental_sync(
                owner_name,
                repo.default_branch,
                cursor.last_after_sha,
            )

        # No cursor - do full first-index
        return self.first_index(owner_name)

    # --- Active-set (#61) ---

    def demote_inactive(self) -> list[dict]:
        """Demote repos idle for > config.inactive_days."""
        results = []
        for repo in self._db.list_active_repos():
            state = get_mirror_state(repo.owner_name, self._config)
            if state is None:
                continue
            if state.last_activity is None:
                continue
            idle_days = (
                datetime.now(UTC) - state.last_activity
            ).days
            if idle_days >= self._config.inactive_days:
                log.info(
                    "Demoting %s (idle %d days)",
                    repo.owner_name,
                    idle_days,
                )
                demote_to_sparse(repo.owner_name, self._config)
                results.append(
                    {
                        "owner_name": repo.owner_name,
                        "action": "demoted",
                        "idle_days": idle_days,
                    }
                )
        return results

    def check_inactive_pool_size(self) -> dict:
        """Check inactive pool disk usage against hard cap."""
        total_bytes = 0
        results = []
        for repo in self._db.list_active_repos():
            state = get_mirror_state(repo.owner_name, self._config)
            if state and state.clone_mode != "full":
                bytes_used = state.disk_bytes or 0
                total_bytes += bytes_used
                results.append(
                    {
                        "owner_name": repo.owner_name,
                        "disk_bytes": bytes_used,
                    }
                )

        pool_gb = self._config.inactive_pool_gb
        used_gb = total_bytes / (1024**3)
        warning = used_gb >= pool_gb * 0.9  # warn at 90%

        return {
            "total_bytes": total_bytes,
            "used_gb": round(used_gb, 1),
            "cap_gb": pool_gb,
            "warning": warning,
            "repos": results,
        }

    # --- Reconciler (#59) ---

    def reconcile_refs(
        self, owner_name: str | None = None
    ) -> list[dict]:
        """Compare catalog SHAs against current refs, repair drift.

        If *owner_name* is given, reconcile only that repo.
        Otherwise reconcile all active repos.
        """
        results: list[dict] = []
        repos = (
            [self._db.get_repo(owner_name)]
            if owner_name
            else self._db.list_active_repos()
        )
        repos = [r for r in repos if r is not None]

        for repo in repos:
            try:
                current_sha = resolve_ref_sha(
                    repo.owner_name,
                    f"refs/remotes/origin/{repo.default_branch}",
                    self._config,
                )
            except RuntimeError:
                log.warning(
                    "Cannot resolve ref for %s, trying direct...",
                    repo.owner_name,
                )
                try:
                    full_clone(repo.owner_name, self._config)
                    current_sha = resolve_ref_sha(
                        repo.owner_name,
                        f"refs/remotes/origin/{repo.default_branch}",
                        self._config,
                    )
                except RuntimeError:
                    log.error(
                        "Still cannot resolve ref for %s",
                        repo.owner_name,
                    )
                    continue

            cursor = self._db.get_cursor(
                repo.id, repo.default_branch
            )
            cursor_sha = cursor.last_after_sha if cursor else None

            if cursor_sha != current_sha:
                log.info(
                    "Reconciling %s: cursor %s != remote %s",
                    repo.owner_name,
                    cursor_sha,
                    current_sha,
                )
                result = self.incremental_sync(
                    owner_name=repo.owner_name,
                    ref_name=repo.default_branch,
                    after_sha=current_sha,
                    before_sha=cursor_sha,
                )
                results.append(
                    {
                        "owner_name": repo.owner_name,
                        "action": "repaired",
                        "from_sha": cursor_sha,
                        "to_sha": current_sha,
                        "detail": result,
                    }
                )
        return results


def _resolve_default_branch(
    owner_name: str, config: IndexerConfig
) -> str:
    """Resolve the default branch for a repo."""
    try:
        return get_repo_default_branch(owner_name, config)
    except RuntimeError:
        return "main"
