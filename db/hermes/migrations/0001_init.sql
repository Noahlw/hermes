-- Hermes DB core schema (Wayfinder #47)
-- Owner: hermes_app (or local ubuntu under trust auth).
-- Apply via /home/<user>/.hermes/db/migrate.sh hermes, which records versions in schema_migrations.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
    id          BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL,
    actor       TEXT,
    persona_id  TEXT,
    task_id     TEXT,
    action      TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance  JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS audit_events_occurred_at_idx
    ON audit_events (occurred_at);

CREATE INDEX IF NOT EXISTS audit_events_action_idx
    ON audit_events (action);

CREATE INDEX IF NOT EXISTS audit_events_persona_task_idx
    ON audit_events (persona_id, task_id);

CREATE TABLE IF NOT EXISTS research_evidence (
    id            BIGSERIAL PRIMARY KEY,
    topic         TEXT NOT NULL,
    claim         TEXT NOT NULL,
    source_uri    TEXT NOT NULL,
    retrieved_at  TIMESTAMPTZ NOT NULL,
    excerpt       TEXT,
    excerpt_hash  TEXT,
    confidence    REAL,
    sensitivity   TEXT NOT NULL DEFAULT 'public'
                  CHECK (sensitivity IN ('public', 'private')),
    persona_id    TEXT,
    task_id       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    supersedes    BIGINT REFERENCES research_evidence(id)
);

CREATE INDEX IF NOT EXISTS research_evidence_topic_idx
    ON research_evidence (topic);

CREATE INDEX IF NOT EXISTS research_evidence_source_idx
    ON research_evidence (source_uri);

CREATE INDEX IF NOT EXISTS research_evidence_persona_task_idx
    ON research_evidence (persona_id, task_id);

CREATE TABLE IF NOT EXISTS persona_task_scopes (
    id          BIGSERIAL PRIMARY KEY,
    persona_id  TEXT NOT NULL,
    task_id     TEXT NOT NULL,
    visibility  TEXT NOT NULL
                CHECK (visibility IN ('private', 'shared')),
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (persona_id, task_id)
);

CREATE TABLE IF NOT EXISTS session_briefs (
    id              BIGSERIAL PRIMARY KEY,
    task            TEXT NOT NULL,
    repos           TEXT[],
    brief_markdown  TEXT NOT NULL,
    citations       JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS session_briefs_task_idx
    ON session_briefs (task);

CREATE TABLE IF NOT EXISTS digest_artifacts (
    id             BIGSERIAL PRIMARY KEY,
    kind           TEXT NOT NULL,
    title          TEXT NOT NULL,
    body_markdown  TEXT NOT NULL,
    topics         TEXT[],
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS digest_artifacts_kind_idx
    ON digest_artifacts (kind);

CREATE INDEX IF NOT EXISTS digest_artifacts_topics_idx
    ON digest_artifacts USING GIN (topics);

CREATE TABLE IF NOT EXISTS digest_allowlists (
    id       BIGSERIAL PRIMARY KEY,
    topic    TEXT NOT NULL UNIQUE,
    enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    config   JSONB NOT NULL DEFAULT '{}'::jsonb
);
