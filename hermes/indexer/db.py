from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from hermes.indexer.config import IndexerConfig

try:
    import psycopg2
    import psycopg2.extras

    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


@dataclass(frozen=True)
class RepoRow:
    id: int
    owner_name: str
    default_branch: str
    status: str  # 'active' | 'revoked'
    revoked_at: datetime | None
    purge_after: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class RepoRefRow:
    id: int
    repo_id: int
    ref_name: str
    pinned_sha: str | None


@dataclass(frozen=True)
class SyncCursorRow:
    id: int
    repo_id: int
    ref_name: str
    last_before_sha: str | None
    last_after_sha: str | None
    last_success_at: datetime | None


class CodebaseIndexDB:
    """Low-level Postgres access for the codebase index database."""

    def __init__(self, config: IndexerConfig) -> None:
        self._config = config
        self._conn: Any = None

    def _connect(self) -> Any:
        if self._conn is None or self._conn.closed:
            if not HAS_PSYCOPG2:
                raise RuntimeError(
                    "psycopg2 is not installed; "
                    "install with: pip install psycopg2-binary"
                )
            kwargs: dict[str, Any] = {
                "host": self._config.db_host,
                "port": self._config.db_port,
                "dbname": self._config.db_name,
                "user": self._config.db_user,
            }
            if self._config.db_password:
                kwargs["password"] = self._config.db_password
            self._conn = psycopg2.connect(**kwargs)
            self._conn.autocommit = False
        return self._conn

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
            self._conn = None

    # -- repos --

    def upsert_repo(
        self, owner_name: str, default_branch: str
    ) -> int:
        """Insert or update a repo catalog row. Returns repo id."""
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO repos (owner_name, default_branch, status)
                   VALUES (%s, %s, 'active')
                   ON CONFLICT (owner_name)
                   DO UPDATE SET default_branch = EXCLUDED.default_branch,
                                 status = 'active',
                                 revoked_at = NULL,
                                 purge_after = NULL
                   RETURNING id""",
                (owner_name, default_branch),
            )
            repo_id = cur.fetchone()[0]
            conn.commit()
        return repo_id

    def get_repo(self, owner_name: str) -> RepoRow | None:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, owner_name, default_branch, status,
                          revoked_at, purge_after, created_at
                   FROM repos WHERE owner_name = %s""",
                (owner_name,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return RepoRow(
            id=row[0],
            owner_name=row[1],
            default_branch=row[2],
            status=row[3],
            revoked_at=row[4],
            purge_after=row[5],
            created_at=row[6],
        )

    def list_active_repos(self) -> list[RepoRow]:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, owner_name, default_branch, status,
                          revoked_at, purge_after, created_at
                   FROM repos WHERE status = 'active'
                   ORDER BY owner_name"""
            )
            return [
                RepoRow(
                    id=r[0],
                    owner_name=r[1],
                    default_branch=r[2],
                    status=r[3],
                    revoked_at=r[4],
                    purge_after=r[5],
                    created_at=r[6],
                )
                for r in cur.fetchall()
            ]

    def revoke_repo(self, owner_name: str) -> datetime:
        """Mark repo as revoked with purge_after = now+30 days."""
        conn = self._connect()
        purge = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE repos
                   SET status = 'revoked',
                       revoked_at = %s,
                       purge_after = %s + INTERVAL '30 days'
                   WHERE owner_name = %s
                   RETURNING purge_after""",
                (purge, purge, owner_name),
            )
            row = cur.fetchone()
            conn.commit()
        if row is None:
            raise ValueError(f"repo {owner_name} not found")
        return row[0]

    def force_purge_repo(self, owner_name: str) -> None:
        """Delete repo and all cascade rows."""
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM repos WHERE owner_name = %s",
                (owner_name,),
            )
            conn.commit()

    # -- repo_refs --

    def upsert_ref(
        self, repo_id: int, ref_name: str, pinned_sha: str | None
    ) -> int:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO repo_refs (repo_id, ref_name, pinned_sha)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (repo_id, ref_name)
                   DO UPDATE SET pinned_sha = EXCLUDED.pinned_sha
                   RETURNING id""",
                (repo_id, ref_name, pinned_sha),
            )
            ref_id = cur.fetchone()[0]
            conn.commit()
        return ref_id

    def get_ref(self, repo_id: int, ref_name: str) -> RepoRefRow | None:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, repo_id, ref_name, pinned_sha
                   FROM repo_refs
                   WHERE repo_id = %s AND ref_name = %s""",
                (repo_id, ref_name),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return RepoRefRow(
            id=row[0], repo_id=row[1], ref_name=row[2], pinned_sha=row[3]
        )

    def list_refs(self, repo_id: int) -> list[RepoRefRow]:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, repo_id, ref_name, pinned_sha
                   FROM repo_refs WHERE repo_id = %s""",
                (repo_id,),
            )
            return [
                RepoRefRow(
                    id=r[0],
                    repo_id=r[1],
                    ref_name=r[2],
                    pinned_sha=r[3],
                )
                for r in cur.fetchall()
            ]

    # -- files --

    def upsert_file(
        self,
        repo_id: int,
        ref_id: int | None,
        path: str,
        language: str | None,
        content_sha: str | None,
        commit_sha: str,
    ) -> int:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO files
                      (repo_id, ref_id, path, language, content_sha, commit_sha)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (repo_id, commit_sha, path)
                   DO UPDATE SET
                       ref_id = EXCLUDED.ref_id,
                       language = EXCLUDED.language,
                       content_sha = EXCLUDED.content_sha
                   RETURNING id""",
                (repo_id, ref_id, path, language, content_sha, commit_sha),
            )
            file_id = cur.fetchone()[0]
            conn.commit()
        return file_id

    def delete_files_not_in(
        self, repo_id: int, commit_sha: str, kept_paths: set[str]
    ) -> None:
        """Remove knowledge rows for paths absent from *kept_paths*."""
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM files
                   WHERE repo_id = %s
                     AND commit_sha = %s
                     AND path != ALL(%s)""",
                (repo_id, commit_sha, list(kept_paths)),
            )
            conn.commit()

    def delete_files_for_repo(self, repo_id: int) -> None:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM files WHERE repo_id = %s", (repo_id,)
            )
            conn.commit()

    # -- symbols --

    def insert_symbol(
        self,
        file_id: int,
        name: str,
        kind: str | None,
        start_line: int,
        end_line: int,
        signature: str | None,
    ) -> None:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO symbols
                      (file_id, name, kind, start_line, end_line, signature)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (file_id, name, kind, start_line, end_line, signature),
            )
            conn.commit()

    def delete_symbols_for_path(
        self,
        repo_id: int,
        path: str,
        commit_sha: str,
    ) -> None:
        """Delete symbol rows for a specific file path at a specific commit."""
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM symbols
                   WHERE file_id IN (
                       SELECT id FROM files
                       WHERE repo_id = %s
                         AND path = %s
                         AND commit_sha = %s
                   )""",
                (repo_id, path, commit_sha),
            )
            conn.commit()

    # -- chunks --

    def insert_chunk(
        self,
        file_id: int,
        chunk_index: int,
        start_line: int,
        end_line: int,
        content: str,
        content_sha: str,
    ) -> None:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO chunks
                      (file_id, chunk_index, start_line, end_line,
                       content, content_sha)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (file_id, chunk_index)
                   DO UPDATE SET
                       start_line = EXCLUDED.start_line,
                       end_line = EXCLUDED.end_line,
                       content = EXCLUDED.content,
                       content_sha = EXCLUDED.content_sha""",
                (
                    file_id,
                    chunk_index,
                    start_line,
                    end_line,
                    content,
                    content_sha,
                ),
            )
            conn.commit()

    def chunk_exists(self, content_sha: str) -> bool:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM chunks WHERE content_sha = %s LIMIT 1",
                (content_sha,),
            )
            return cur.fetchone() is not None

    # -- sync_cursors --

    def upsert_cursor(
        self,
        repo_id: int,
        ref_name: str,
        before_sha: str | None,
        after_sha: str | None,
    ) -> None:
        conn = self._connect()
        now = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO sync_cursors
                      (repo_id, ref_name, last_before_sha,
                       last_after_sha, last_success_at)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (repo_id, ref_name)
                   DO UPDATE SET
                       last_before_sha = EXCLUDED.last_before_sha,
                       last_after_sha = EXCLUDED.last_after_sha,
                       last_success_at = EXCLUDED.last_success_at""",
                (repo_id, ref_name, before_sha, after_sha, now),
            )
            conn.commit()

    def get_cursor(
        self, repo_id: int, ref_name: str
    ) -> SyncCursorRow | None:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, repo_id, ref_name,
                          last_before_sha, last_after_sha, last_success_at
                   FROM sync_cursors
                   WHERE repo_id = %s AND ref_name = %s""",
                (repo_id, ref_name),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return SyncCursorRow(
            id=row[0],
            repo_id=row[1],
            ref_name=row[2],
            last_before_sha=row[3],
            last_after_sha=row[4],
            last_success_at=row[5],
        )

    def get_all_cursors(self) -> list[SyncCursorRow]:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, repo_id, ref_name,
                          last_before_sha, last_after_sha, last_success_at
                   FROM sync_cursors
                   ORDER BY repo_id, ref_name"""
            )
            return [
                SyncCursorRow(
                    id=r[0],
                    repo_id=r[1],
                    ref_name=r[2],
                    last_before_sha=r[3],
                    last_after_sha=r[4],
                    last_success_at=r[5],
                )
                for r in cur.fetchall()
            ]

    # -- search / query --

    def search_chunks(
        self, query: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Postgres FTS search over chunks."""
        conn = self._connect()
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(
                """SELECT c.id, c.file_id, c.chunk_index,
                          c.start_line, c.end_line,
                          LEFT(c.content, 500) AS snippet,
                          c.content_sha,
                          f.path, f.language,
                          f.commit_sha,
                          r.owner_name
                   FROM chunks c
                   JOIN files f ON f.id = c.file_id
                   JOIN repos r ON r.id = f.repo_id
                   WHERE c.tsv @@ plainto_tsquery('english', %s)
                   ORDER BY ts_rank(c.tsv, plainto_tsquery('english', %s)) DESC
                   LIMIT %s""",
                (query, query, limit),
            )
            return [dict(r) for r in cur.fetchall()]
