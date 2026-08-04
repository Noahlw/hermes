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
        # cron weekdays: 0=Sunday, 1=Monday, 3=Wednesday.
        assert s.matches(datetime(2026, 8, 3, 7, 0, tzinfo=timezone.utc))  # Monday
        assert s.matches(datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc))  # Wednesday
        assert not s.matches(datetime(2026, 8, 4, 7, 0, tzinfo=timezone.utc))  # Tuesday

    def test_weekday_zero_is_sunday(self) -> None:
        s = CronSchedule.parse("0 6 * * 0")
        assert s.matches(datetime(2026, 8, 2, 6, 0, tzinfo=timezone.utc))  # Sunday
        assert not s.matches(datetime(2026, 8, 3, 6, 0, tzinfo=timezone.utc))  # Monday

    def test_invalid_expression_raises(self) -> None:
        with pytest.raises(ValueError):
            CronSchedule.parse("0 6 * *")
        with pytest.raises(ValueError):
            CronSchedule.parse("0 25 * * *")
        with pytest.raises(ValueError):
            CronSchedule.parse("0 6 * 13 *")


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

def _loaded(path) -> CronScheduler:
    sched = CronScheduler(path)
    sched.load()
    return sched


def test_due_jobs_respects_enabled_and_schedule(
    tmp_path: pytest.TempPathFactory,
) -> None:
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(_jobs_doc()))
    sched = _loaded(path)
    now = datetime(2026, 8, 4, 6, 0, tzinfo=timezone.utc)
    due = {j.id for j in sched.due_jobs(now)}
    assert "daily-job" in due
    assert "disabled-job" not in due
    assert "interval-job" in due  # first run: interval elapsed


def test_due_jobs_interval_not_rerun_within_window(
    tmp_path: pytest.TempPathFactory,
) -> None:
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(_jobs_doc()))
    sched = _loaded(path)
    import time

    assert "interval-job" in {j.id for j in sched.due_jobs()}  # never run
    sched._jobs[2].last_run_at = time.time() - 3540  # 59 min ago: inside window
    assert "interval-job" not in {j.id for j in sched.due_jobs()}
    sched._jobs[2].last_run_at = time.time() - 3660  # 61 min ago: window elapsed
    assert "interval-job" in {j.id for j in sched.due_jobs()}


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
        "command": "touch",
        "args": [str(marker)],
        "schedule": "* * * * *",
        "log_file": str(log_file),
    }
    path.write_text(json.dumps({"jobs": [job]}))
    sched = _loaded(path)
    sched.run_job(sched.jobs[0])
    assert marker.exists()
    assert log_file.exists()
    text = log_file.read_text()
    assert "exit 0" in text
    assert "+ touch" in text  # header: [timestamp] + argv


def test_run_job_records_nonzero_exit(
    tmp_path: pytest.TempPathFactory,
) -> None:
    path = tmp_path / "jobs.json"
    log_file = tmp_path / "fail.log"
    import sys

    job = {
        "id": "f",
        "name": "F",
        "enabled": True,
        "command": sys.executable,
        "args": ["-c", "raise SystemExit(1)"],
        "schedule": "* * * * *",
        "log_file": str(log_file),
    }
    path.write_text(json.dumps({"jobs": [job]}))
    sched = _loaded(path)
    sched.run_job(sched.jobs[0])
    assert "exit 1" in log_file.read_text()


def test_load_skips_invalid_schedule_keeps_valid(
    tmp_path: pytest.TempPathFactory,
) -> None:
    path = tmp_path / "jobs.json"
    path.write_text(
        json.dumps(
            _jobs_doc(
                [{"id": "bad", "name": "B", "enabled": True,
                  "command": "/bin/true", "schedule": "oops",
                  "log_file": "/tmp/bad.log"}]
            )
        )
    )
    sched = _loaded(path)
    ids = {j.id for j in sched.jobs}
