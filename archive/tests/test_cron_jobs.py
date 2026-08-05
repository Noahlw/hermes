"""Tests for the Hermes cron jobs schema.

Validates that ``cron/jobs.json`` meets the structural requirements expected
by hermes-agent's InProcessCronScheduler. This is a **schema validation** —
not testing the scheduler itself, but that the deployment artifact is well-
formed for the existing runtime.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CRON_JSON = REPO_ROOT / "cron" / "jobs.json"

REQUIRED_JOB_KEYS = frozenset({"id", "name", "enabled", "command"})
SCHEDULE_KEYS = frozenset({"schedule", "interval_minutes"})

# Hard-coded expectations from the portable-restore ticket (#48 / #53)
EXPECTED_JOB_IDS: set[str] = {
    "hermes-health-check",
    "ollama-keep-alive",
    "portable-postgres-backup",
    "neo4j-drive-backup",
}

# Jobs that are known to belong to the portable-restore feature
PORTABLE_RESTORE_IDS = {"portable-postgres-backup", "neo4j-drive-backup"}


class CronJsonExistsTests(unittest.TestCase):
    """The cron/jobs.json file exists and is valid JSON."""

    def test_file_exists(self) -> None:
        self.assertTrue(CRON_JSON.is_file(), f"{CRON_JSON} not found")

    def test_valid_json(self) -> None:
        with open(CRON_JSON) as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)


class CronJsonTopLevelTests(unittest.TestCase):
    """Top-level structure of jobs.json."""

    def setUp(self) -> None:
        with open(CRON_JSON) as f:
            self.data = json.load(f)

    def test_has_jobs_list(self) -> None:
        jobs = self.data.get("jobs")
        self.assertIsNotNone(jobs, "missing 'jobs' key")
        self.assertIsInstance(jobs, list)

    def test_all_expected_jobs_present(self) -> None:
        ids = {j["id"] for j in self.data.get("jobs", [])}
        missing = EXPECTED_JOB_IDS - ids
        self.assertSetEqual(
            missing, set(), f"Expected job IDs not found: {missing}"
        )


class CronJobValidationTests(unittest.TestCase):
    """Each job entry is structurally sound."""

    def setUp(self) -> None:
        with open(CRON_JSON) as f:
            self.jobs = json.load(f)["jobs"]
        self.all_jobs: list[dict] = self.jobs

    def test_all_jobs_required_keys(self) -> None:
        """Every job must have id, name, enabled, command."""
        for job in self.all_jobs:
            missing = REQUIRED_JOB_KEYS - job.keys()
            self.assertSetEqual(
                missing,
                set(),
                f"Job '{job.get('id', '?')}' missing keys: {missing}",
            )

    def test_all_jobs_have_schedule_or_interval(self) -> None:
        """Every job must have at least 'schedule' or 'interval_minutes'."""
        for job in self.all_jobs:
            has = SCHEDULE_KEYS & job.keys()
            self.assertTrue(
                has,
                f"Job '{job.get('id', '?')}' has neither schedule "
                f"nor interval_minutes",
            )

    def test_all_job_ids_are_unique(self) -> None:
        ids = [j["id"] for j in self.all_jobs]
        dupes = {i for i in ids if ids.count(i) > 1}
        self.assertSetEqual(dupes, set(), f"Duplicate job ids: {dupes}")

    def test_unknown_job_ids_not_added(self) -> None:
        """Warn if a job id appears that is not in the expected set."""
        ids = {j["id"] for j in self.all_jobs}
        extra = ids - EXPECTED_JOB_IDS
        if extra:
            self.fail(f"Unexpected job ids (add to EXPECTED_JOB_IDS?): {extra}")


class CronPortableRestoreTests(unittest.TestCase):
    """Ticket #53 / #48: portable-restore job states and the Neo4j retired job."""

    def setUp(self) -> None:
        with open(CRON_JSON) as f:
            self.jobs = json.load(f)["jobs"]
        self._jobs_by_id = {j["id"]: j for j in self.jobs}

    def _job(self, job_id: str) -> dict | None:
        return self._jobs_by_id.get(job_id)

    # -- portable-postgres-backup --

    def test_portable_backup_is_enabled(self) -> None:
        job = self._job("portable-postgres-backup")
        self.assertIsNotNone(job)
        self.assertTrue(job["enabled"])

    def test_portable_backup_has_cron_schedule(self) -> None:
        job = self._job("portable-postgres-backup")
        self.assertIn("schedule", job)

    def test_portable_backup_has_log_file(self) -> None:
        job = self._job("portable-postgres-backup")
        self.assertIn("log_file", job)
        self.assertIsInstance(job["log_file"], str)

    def test_portable_backup_has_command(self) -> None:
        job = self._job("portable-postgres-backup")
        self.assertIn("command", job)
        self.assertIn("backup_postgres_drive.sh", job["command"])

    # -- neo4j-drive-backup (retired) --

    def test_neo4j_backup_is_disabled(self) -> None:
        job = self._job("neo4j-drive-backup")
        self.assertIsNotNone(job)
        self.assertFalse(job["enabled"])

    def test_neo4j_backup_uses_interval_minutes(self) -> None:
        """Neo4j backup is an interval-based (not cron) job."""
        job = self._job("neo4j-drive-backup")
        self.assertIn("interval_minutes", job)
        self.assertIsInstance(job["interval_minutes"], int)


class CronExistingJobsNotRemovedTests(unittest.TestCase):
    """Reboot contract (map #76 Task 6, 2026-08-04): legacy VM paths are
    gone, the dead vm-health-check is replaced by hermes-health-check,
    weekly-workspace-cleanup is dropped (script lost with old VM), and
    ollama-keep-alive is re-enabled since D-C landed (local Ollama
    embeddings, 2026-08-04)."""

    def setUp(self) -> None:
        with open(CRON_JSON) as f:
            self.jobs_by_id = {j["id"]: j for j in json.load(f)["jobs"]}


    def test_hermes_health_check_present(self) -> None:
        self.assertIn("hermes-health-check", self.jobs_by_id)

    def test_ollama_keep_alive_present(self) -> None:
        self.assertIn("ollama-keep-alive", self.jobs_by_id)


    def test_vm_health_check_replaced(self) -> None:
        """Dead vm-health-check is gone; its schedule lives on under the
        new id (ops-digest is one hour later at 0 7 * * *)."""
        self.assertNotIn("vm-health-check", self.jobs_by_id)
        self.assertTrue(self.jobs_by_id["hermes-health-check"]["enabled"])

    def test_vm_health_check_has_cron_schedule(self) -> None:
        self.assertIn("schedule", self.jobs_by_id["hermes-health-check"])

    def test_weekly_workspace_cleanup_removed(self) -> None:
        """Script lost with the old VM; confirm-delete flow is
        design-captured only (CONTEXT.md), so the job is dropped."""
        self.assertNotIn("weekly-workspace-cleanup", self.jobs_by_id)

    def test_ollama_keep_alive_enabled(self) -> None:
        """D-C landed: local Ollama serves embeddings on the target."""
        self.assertTrue(self.jobs_by_id["ollama-keep-alive"]["enabled"])

    def test_no_job_uses_legacy_vm_path(self) -> None:
        """Reboot contract: no job references /home/ubuntu/.hermes."""
        for job in self.jobs_by_id.values():
            blob = " ".join(
                str(v) for v in (job.get("command"), job.get("log_file")) if v
            )
            self.assertNotIn("/home/ubuntu/.hermes", blob)


if __name__ == "__main__":
    unittest.main()
