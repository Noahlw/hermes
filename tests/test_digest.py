"""Tests for the daily ops digest formatter (Ticket 72)."""

from __future__ import annotations

import json
import unittest

from hermes.digest.formatter import (
    CronJobStatus,
    DigestEntry,
    format_digest,
    format_digest_for_db,
    format_digest_markdown,
    token_count,
)


class DigestFormatterTests(unittest.TestCase):
    """Tests for digest formatting and token budget enforcement."""

    def setUp(self) -> None:
        self.sample_entries = [
            DigestEntry(
                job_id="vm-health-check",
                job_name="VM health check",
                status=CronJobStatus.HEALTHY,
                details="All services responsive",
            ),
            DigestEntry(
                job_id="ollama-keep-alive",
                job_name="Ollama keep-alive",
                status=CronJobStatus.HEALTHY,
                details="Model server online",
            ),
            DigestEntry(
                job_id="weekly-workspace-cleanup",
                job_name="Weekly workspace cleanup",
                status=CronJobStatus.FAILED,
                details="HTTP 401 — GDrive auth expired",
            ),
            DigestEntry(
                job_id="portable-postgres-backup",
                job_name="Portable Postgres backup",
                status=CronJobStatus.HEALTHY,
                details="Backup completed: 42 MB",
            ),
            DigestEntry(
                job_id="ops-digest",
                job_name="Daily ops digest",
                status=CronJobStatus.NEVER_RUN,
                details="First run pending",
            ),
        ]

    def test_format_digest_markdown_has_header(self) -> None:
        markdown = format_digest_markdown(self.sample_entries)
        self.assertIn("Hermes Daily Ops Digest", markdown)

    def test_format_digest_markdown_window_in_header(self) -> None:
        markdown = format_digest_markdown(
            self.sample_entries,
            window_start="2026-07-29T00:00:00Z",
            window_end="2026-07-30T00:00:00Z",
        )
        self.assertIn("2026-07-29", markdown)
        self.assertIn("2026-07-30", markdown)

    def test_format_digest_markdown_has_all_entries(self) -> None:
        markdown = format_digest_markdown(self.sample_entries)
        for entry in self.sample_entries:
            self.assertIn(entry.job_name, markdown)

    def test_format_digest_markdown_has_status_values(self) -> None:
        markdown = format_digest_markdown(self.sample_entries)
        self.assertIn("healthy", markdown)
        self.assertIn("failed", markdown)
        self.assertIn("never_run", markdown)

    def test_format_digest_markdown_empty_entries_is_valid(self) -> None:
        markdown = format_digest_markdown([])
        self.assertIn("Hermes Daily Ops Digest", markdown)

    def test_format_digest_under_token_budget(self) -> None:
        result = format_digest(self.sample_entries)
        data = json.loads(result.details)
        count = token_count(data["summary_markdown"])
        self.assertLessEqual(count, 200)
        self.assertGreater(count, 0)

    def test_format_digest_stays_under_token_budget_with_huge_details(self) -> None:
        """Budget enforced by per-entry truncation in format_digest_markdown."""
        huge_entries = [
            DigestEntry(
                job_id="test",
                job_name="Test job",
                status=CronJobStatus.FAILED,
                details="very long details " * 500,
            )
        ]
        result = format_digest(huge_entries)
        data = json.loads(result.details)
        count = token_count(data["summary_markdown"])
        self.assertLessEqual(count, 200)

    def test_format_digest_for_db_returns_three_fields(self) -> None:
        summary, per_job_json, per_job_list = format_digest_for_db(
            self.sample_entries,
            window_start="2026-07-29",
            window_end="2026-07-30",
        )
        self.assertIsInstance(summary, str)
        self.assertTrue(summary)
        parsed = json.loads(per_job_json)
        self.assertIsInstance(parsed, list)
        self.assertEqual(len(parsed), len(self.sample_entries))
        self.assertEqual(per_job_list, parsed)

    def test_format_digest_for_db_summary_is_markdown(self) -> None:
        summary, _j, _l = format_digest_for_db(self.sample_entries)
        self.assertIn("**", summary)

    def test_format_digest_for_db_per_job_has_required_fields(self) -> None:
        _s, _j, per_job_list = format_digest_for_db(self.sample_entries)
        for entry in per_job_list:
            self.assertIn("job_id", entry)
            self.assertIn("job_name", entry)
            self.assertIn("status", entry)
            self.assertIn("details", entry)

    def test_token_count_simple_text(self) -> None:
        self.assertEqual(token_count("hello world"), 2)
        self.assertEqual(token_count("hello\nworld"), 3)

    def test_token_count_markdown(self) -> None:
        text = "**Hermes Daily Ops Digest**\n\n✅ **VM health check** — healthy"
        count = token_count(text)
        self.assertGreater(count, 5)
        self.assertLess(count, 20)

    def test_digest_entry_status_icon(self) -> None:
        self.assertEqual(
            DigestEntry("id", "name", CronJobStatus.HEALTHY).status_icon, "✅"
        )
        self.assertEqual(
            DigestEntry("id", "name", CronJobStatus.FAILED).status_icon, "❌"
        )
        self.assertEqual(
            DigestEntry("id", "name", CronJobStatus.STALE).status_icon, "⚠️"
        )
        self.assertEqual(
            DigestEntry("id", "name", CronJobStatus.NEVER_RUN).status_icon, "🔹"
        )

    # --- Acceptance tests from #72 ---

    def test_all_registered_jobs_represented(self) -> None:
        """Acceptance: every registered cron job gets one status line."""
        markdown = format_digest_markdown(self.sample_entries)
        for entry in self.sample_entries:
            self.assertIn(entry.job_name, markdown)
        status_lines = [
            line for line in markdown.split("\n")
            if any(icon in line for icon in ("✅", "❌", "⚠️", "🔹"))
        ]
        self.assertEqual(len(status_lines), len(self.sample_entries))

    def test_token_budget_enforced(self) -> None:
        """Acceptance: ≤200-token budget is enforced."""
        result = format_digest(self.sample_entries)
        data = json.loads(result.details)
        self.assertLessEqual(token_count(data["summary_markdown"]), 200)

    def test_per_job_status_includes_failed_state(self) -> None:
        """Acceptance: failed job status is explicitly surfaced."""
        _s, _j, per_job = format_digest_for_db(self.sample_entries)
        failed = [j for j in per_job if j["status"] == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["job_id"], "weekly-workspace-cleanup")
        self.assertIn("401", failed[0]["details"])

    def test_per_job_status_includes_never_run_state(self) -> None:
        """Acceptance: never-run job status is explicitly surfaced."""
        _s, _j, per_job = format_digest_for_db(self.sample_entries)
        never_run = [j for j in per_job if j["status"] == "never_run"]
        self.assertEqual(len(never_run), 1)
        self.assertEqual(never_run[0]["job_id"], "ops-digest")

    def test_digest_is_reproducible(self) -> None:
        """Acceptance: format is deterministic — same input → same output."""
        result1 = format_digest(self.sample_entries)
        result2 = format_digest(self.sample_entries)
        self.assertEqual(result1, result2)

    def test_format_digest_for_db_json_is_valid(self) -> None:
        """Acceptance: per_job_status is valid JSON for the digests table."""
        _s, per_job_json, _l = format_digest_for_db(self.sample_entries)
        parsed = json.loads(per_job_json)
        self.assertIsInstance(parsed, list)
        for entry in parsed:
            self.assertIsInstance(entry, dict)
            self.assertIn("job_id", entry)


class DBMigrationTests(unittest.TestCase):
    """Shape check for the digests migration file."""

    def _migration_content(self) -> str:
        from pathlib import Path
        migration = (
            Path(__file__).resolve().parent.parent
            / "db" / "hermes" / "migrations" / "0002_digests.sql"
        )
        return migration.read_text()

    def test_migration_creates_digests_table(self) -> None:
        content = self._migration_content()
        self.assertIn("CREATE TABLE IF NOT EXISTS digests", content)

    def test_migration_includes_required_columns(self) -> None:
        content = self._migration_content()
        for col in ("id", "created_at", "window_start", "window_end",
                     "summary_markdown", "per_job_status"):
            self.assertIn(col, content, f"Missing column '{col}'")

    def test_migration_includes_indexes(self) -> None:
        content = self._migration_content()
        self.assertIn("CREATE INDEX", content)
        self.assertIn("digests_created_at_idx", content)
        self.assertIn("digests_window_idx", content)

    def test_migration_follows_existing_convention(self) -> None:
        from pathlib import Path
        migration_dir = (
            Path(__file__).resolve().parent.parent
            / "db" / "hermes" / "migrations"
        )
        files = sorted(migration_dir.glob("*.sql"))
        self.assertIn(migration_dir / "0002_digests.sql", files)


if __name__ == "__main__":
    unittest.main()
