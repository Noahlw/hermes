-- Hermes DB: digests table (Wayfinder #62, Ticket 72)
-- Stores daily ops digests produced by the main_agent cron job.
-- Apply via /home/<user>/.hermes/db/migrate.sh hermes.

CREATE TABLE IF NOT EXISTS digests (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    window_start    TIMESTAMPTZ NOT NULL,
    window_end      TIMESTAMPTZ NOT NULL,
    summary_markdown TEXT NOT NULL DEFAULT '',
    per_job_status   JSONB NOT NULL DEFAULT '[]'::jsonb
);

COMMENT ON TABLE digests IS
'Daily ops digests from the main_agent run_ops_digest cron job (Issue #62).';

COMMENT ON COLUMN digests.created_at IS
'Row insert time — when the digest was persisted.';

COMMENT ON COLUMN digests.window_start IS
'Start of the reporting window (inclusive).';

COMMENT ON COLUMN digests.window_end IS
'End of the reporting window (exclusive).';

COMMENT ON COLUMN digests.summary_markdown IS
'Rendered digest prose (≤200 tokens, one-line status per job).';

COMMENT ON COLUMN digests.per_job_status IS
'Structured per-job status: [{"job_id":"...","job_name":"...","status":"healthy|failed|stale|never_run","details":"..."}].';

CREATE INDEX IF NOT EXISTS digests_created_at_idx
    ON digests (created_at DESC);

CREATE INDEX IF NOT EXISTS digests_window_idx
    ON digests (window_start, window_end);
