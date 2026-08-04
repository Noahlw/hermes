"""CronScheduler contract tests (map #76 Task 5, hermes_agent)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from hermes_agent.cron_scheduler import CronSchedule, CronScheduler


class TestCronSchedule:
    def test_parse_and_match_daily(self) -> None:
        s = CronSchedule.parse("0 6 * * *")
        assert s.matches(datetime(2026, 8, 4, 6, 0, tzinfo=timezone.utc))
        assert not s.matches(datetime(2026, 8, 4, 6, 1, tzinfo=timezone.utc))
        assert not s.matches(datetime(2026, 8, 4, 5, 0, tzinfo=timezone.utc))

    def test_parse_and_match_every_n_minutes(self) -> None:
        s = CronSchedule.parse("*/30 * * * *")
        assert s.matches(datetime(2026, 8, 4, 0, 0, tzinfo=timezone.utc))
        assert s.matches(datetime(2026, 8, 4, 0, 30, tzinfo=timezone.utc))
        assert not s.matches(datetime(2026, 8, 4, 0, 15, tzinfo=timezone.utc))

    def test_parse_range_and_list(self) -> None:
        s = CronSchedule.parse("0 6-8 * * 1,3")
        assert s.matches(datetime(2026, 8, 3, 7, 0, tzinfo=timezone.utc))  # Monday
        assert s.matches(datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc))  # Wednesday
        assert not s.matches(datetime(2026, 8, 4, 7, 0, tzinfo=timezone.utc))  # Tuesday

    def test_invalid_expression_raises(self) -> None:
        with pytest.raises(ValueError):
            CronSchedule.parse("0 6 * *")
        with pytest.raises(ValueError):
            CronSchedule.parse("0 25 * * *")


def _jobs_doc(extra_jobs: list[dict] | None = None) -> dict:
    jobs = [
        {
            "id": "daily-job",
            "name": "Daily",
            "enabled": True,
            "command": "/bin/true",
            "schedule": "0 6 * * *",
            "log_file": "/tmp/daily.log",
        },
        {
            "id": "disabled-job",
            "name": "Disabled",
            "enabled": False,
            "command": "/bin/false",
            "schedule": "* * * * *",
            "log_file": "/tmp/disabled.log",
        },
        {
            "id": "interval-job",
            "name": "Interval",
            "enabled": True,
            "command": "/bin/true",
            "interval_minutes": 60,
            "log_file": "/tmp/interval.log",
        },
    ]
    jobs.extend(extra_jobs or [])
    return {"jobs": jobs}


def test_due_jobs_respects_enabled_and_schedule(
    tmp_path: pytest.TempPathFactory,
) -> None:
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(_jobs_doc()))
    sched = CronScheduler(path)
    now = datetime(2026, 8, 4, 6, 0, tzinfo=timezone.utc)
    due = {j["id"] for j in sched.due_jobs(now)}
    assert "daily-job" in due
    assert "disabled-job" not in due
    assert "interval-job" in due  # first run: interval elapsed


def test_due_jobs_interval_not_rerun_within_window(
    tmp_path: pytest.TempPathFactory,
) -> None:
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(_jobs_doc()))
    sched = CronScheduler(path)
    t0 = datetime(2026, 8, 4, 0, 0, tzinfo=timezone.utc)
    assert "interval-job" in {j["id"] for j in sched.due_jobs(t0)}
    sched._last_run["interval-job"] = t0
    assert "interval-job" not in {j["id"] for j in sched.due_jobs(t0 + 60)}
    assert "interval-job" in {j["id"] for j in sched.due_jobs(t0 + 3601)}


def test_run_job_executes_command_and_writes_log(
    tmp_path: pytest.TempPathFactory,
) -> None:
    path = tmp_path / "jobs.json"
    log_file = tmp_path / "out.log"
    marker = tmp_path / "marker"
    job = {
        "id": "t",
        "name": "T",
        "enabled": True,
        "command": f"touch {marker}",
        "schedule": "* * * * *",
        "log_file": str(log_file),
    }
    path.write_text(json.dumps({"jobs": [job]}))
    sched = CronScheduler(path)
    sched.run_job(job)
    assert marker.exists()
    assert log_file.exists()
    text = log_file.read_text()
    assert "exit 0" in text
    assert "[t]" in text


def test_run_job_records_nonzero_exit(
    tmp_path: pytest.TempPathFactory,
) -> None:
    path = tmp_path / "jobs.json"
    log_file = tmp_path / "fail.log"
    job = {
        "id": "f",
        "name": "F",
        "enabled": True,
        "command": "/bin/false",
        "schedule": "* * * * *",
        "log_file": str(log_file),
    }
    path.write_text(json.dumps({"jobs": [job]}))
    sched = CronScheduler(path)
    sched.run_job(job)
    assert "exit 1" in log_file.read_text()


def test_load_skips_disabled_jobs(tmp_path: pytest.TempPathFactory) -> None:
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(_jobs_doc()))
    sched = CronScheduler(path)
    assert {j["id"] for j in sched.jobs} == {
        "daily-job",
        "disabled-job",
        "interval-job",
    }
    assert [j["id"] for j in sched.enabled_jobs] == ["daily-job", "interval-job"]
