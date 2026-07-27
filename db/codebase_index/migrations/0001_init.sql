-- Codebase index DB schema (Wayfinder #47 + #40 indexer)
-- Apply via /home/<user>/.hermes/db/migrate.sh codebase_index.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS schema_meta (
    key    TEXT PRIMARY KEY,
    value  JSONB NOT NULL
);

INSERT INTO schema_meta (key, value) VALUES
    ('embedding_default_dim', jsonb_build_object('dim', 768, 'units', 'vector(768)')),
    ('embedding_default_model', jsonb_build_object('model', 'nomic-embed-text', 'source', 'ollama'))
ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS repos (
    id            BIGSERIAL PRIMARY KEY,
    owner_name    TEXT NOT NULL,  -- "owner/name" canonical form
    default_branch TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active', 'revoked')),
    revoked_at    TIMESTAMPTZ,
    purge_after   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_name)
);

CREATE INDEX IF NOT EXISTS repos_status_idx
    ON repos (status);

CREATE TABLE IF NOT EXISTS repo_refs (
    id         BIGSERIAL PRIMARY KEY,
    repo_id    BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    ref_name   TEXT NOT NULL,
    pinned_sha TEXT,
    UNIQUE (repo_id, ref_name)
);

CREATE TABLE IF NOT EXISTS files (
    id          BIGSERIAL PRIMARY KEY,
    repo_id     BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    ref_id      BIGINT REFERENCES repo_refs(id) ON DELETE CASCADE,
    path        TEXT NOT NULL,
    language    TEXT,
    content_sha TEXT,
    commit_sha  TEXT NOT NULL,
    UNIQUE (repo_id, commit_sha, path)
);

CREATE INDEX IF NOT EXISTS files_repo_path_idx
    ON files (repo_id, path);

CREATE TABLE IF NOT EXISTS symbols (
    id         BIGSERIAL PRIMARY KEY,
    file_id    BIGINT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    kind       TEXT,
    start_line INTEGER,
    end_line   INTEGER,
    signature  TEXT
);

CREATE INDEX IF NOT EXISTS symbols_file_name_idx
    ON symbols (file_id, name);

CREATE TABLE IF NOT EXISTS chunks (
    id          BIGSERIAL PRIMARY KEY,
    file_id     BIGINT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    start_line  INTEGER,
    end_line    INTEGER,
    content     TEXT NOT NULL,
    content_sha TEXT NOT NULL,
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    UNIQUE (file_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS chunks_tsv_idx
    ON chunks USING GIN (tsv);

CREATE INDEX IF NOT EXISTS chunks_content_sha_idx
    ON chunks (content_sha);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id    BIGINT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    model       TEXT NOT NULL,
    dims        INTEGER NOT NULL,
    embedding   vector(768) NOT NULL,
    content_sha TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_cursors (
    id                BIGSERIAL PRIMARY KEY,
    repo_id           BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    ref_name          TEXT NOT NULL,
    last_before_sha   TEXT,
    last_after_sha    TEXT,
    last_success_at   TIMESTAMPTZ,
    UNIQUE (repo_id, ref_name)
);
