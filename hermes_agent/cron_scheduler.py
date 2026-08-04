"""In-process cron scheduler.

Loads jobs from ``cron/jobs.json`` and runs due jobs every 30 seconds.
Each job runs ``subprocess.run([command] + args, timeout=3600)`` with
stdout/stderr appended to ``log_file``. Single-flight per job id —
two ticks cannot run the same job concurrently.

Cron expression grammar (5 fields, plain integer ranges):

    *        -> always
    */n      -> every n (e.g. */30)
    a-b      -> inclusive range
    a,b,c    -> list

No names (no ``MON``), no ``@daily``. jobs.json uses plain 5-field.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("hermes_agent")

TICK_SECONDS: float = 30.0
JOB_TIMEOUT_SECONDS: int = 3600
DEFAULT_JOBS_PATH: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cron", "jobs.json"
)


class CronParseError(ValueError):
    """Raised when a cron expression cannot be parsed."""


@dataclass(frozen=True)
class CronSchedule:
    """Parsed 5-field cron expression."""

    minute: tuple[int, ...]
    hour: tuple[int, ...]
    day: tuple[int, ...]
    month: tuple[int, ...]
    weekday: tuple[int, ...]

    _FIELD_RANGES: tuple[tuple[int, int], ...] = field(
        default=(  # type: ignore[assignment]
            (0, 59),
            (0, 23),
            (1, 31),
            (1, 12),
            (0, 6),
        ),
        init=False,
        repr=False,
        compare=False,
    )

    @classmethod
    def parse(cls, expr: str) -> "CronSchedule":
        """Parse a 5-field cron expression. Raises ``CronParseError``."""
        parts = expr.strip().split()
        if len(parts) != 5:
            raise CronParseError(
                f"cron expression must have 5 fields, got {len(parts)}: {expr!r}"
            )
        try:
            fields = [
                cls._parse_field(parts[i], lo, hi)
                for i, (lo, hi) in enumerate(cls._FIELD_RANGES)
            ]
        except CronParseError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CronParseError(f"invalid cron expression {expr!r}: {exc}") from exc
        return cls(minute=fields[0], hour=fields[1], day=fields[2], month=fields[3], weekday=fields[4])

    @staticmethod
    def _parse_field(token: str, lo: int, hi: int) -> tuple[int, ...]:
        """Parse one cron field. Supports ``*``, ``*/n``, ``a-b``, ``a,b``."""
        token = token.strip()
        if not token:
            raise CronParseError("empty cron field")

        values: set[int] = set()
        for part in token.split(","):
            step = 1
            if "/" in part:
                base, step_str = part.split("/", 1)
                try:
                    step = int(step_str)
                except ValueError as exc:
                    raise CronParseError(f"bad step in {part!r}") from exc
                if step <= 0:
                    raise CronParseError(f"step must be > 0 in {part!r}")
            else:
                base = part

            if base == "*":
                lo_eff, hi_eff = lo, hi
            elif "-" in base:
                a, b = base.split("-", 1)
                try:
                    lo_eff, hi_eff = int(a), int(b)
                except ValueError as exc:
                    raise CronParseError(f"bad range in {part!r}") from exc
                if lo_eff > hi_eff:
                    raise CronParseError(f"reversed range in {part!r}")
            else:
                try:
                    val = int(base)
                except ValueError as exc:
                    raise CronParseError(f"not an integer: {base!r}") from exc
                if step == 1:
                    values.add(val)
                    continue
                lo_eff, hi_eff = val, hi

            if lo_eff < lo or hi_eff > hi:
                raise CronParseError(
                    f"value out of range [{lo}-{hi}] in {part!r}"
                )
            cur = lo_eff
            while cur <= hi_eff:
                values.add(cur)
                cur += step

        if not values:
            raise CronParseError(f"empty value set for field {token!r}")
        return tuple(sorted(values))

    def matches(self, dt: datetime) -> bool:
        """Return True if *dt* (UTC-aware or naive treated as UTC) matches."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return (
            dt.minute in self.minute
            and dt.hour in self.hour
            and dt.day in self.day
            and dt.month in self.month
            and dt.weekday() in self.weekday
        )


@dataclass
class _Job:
    """Runtime representation of one jobs.json entry."""

    id: str
    name: str
    enabled: bool
    command: str
    args: list[str]
    schedule: CronSchedule | None
    interval_minutes: int
    log_file: str
    last_run_at: float = 0.0  # monotonic seconds; 0 = never


def _parse_jobs(data: dict[str, Any]) -> list[_Job]:
    jobs: list[_Job] = []
    for raw in data.get("jobs", []):
        if not isinstance(raw, dict):
            logger.warning("[cron] skipping non-dict job entry: %r", raw)
            continue
        schedule: CronSchedule | None = None
        sched_expr = raw.get("schedule")
        if sched_expr:
            try:
                schedule = CronSchedule.parse(str(sched_expr))
            except CronParseError as exc:
                logger.warning(
                    "[cron] job %s has invalid schedule %r: %s — skipping",
                    raw.get("id"),
                    sched_expr,
                    exc,
                )
                continue
        interval = int(raw.get("interval_minutes") or 0)
        try:
            jobs.append(
                _Job(
                    id=str(raw["id"]),
                    name=str(raw.get("name", raw["id"])),
                    enabled=bool(raw.get("enabled", True)),
                    command=str(raw["command"]),
                    args=list(raw.get("args", []) or []),
                    schedule=schedule,
                    interval_minutes=interval,
                    log_file=str(raw["log_file"]),
                )
            )
        except KeyError as exc:
            logger.warning("[cron] job missing key %s: %r", exc, raw)
    return jobs


class CronScheduler:
    """Loads jobs.json and ticks them every 30 s.

    Public surface is intentionally narrow: ``start`` (asyncio task),
    ``stop``, ``due_jobs`` (test seam), ``run_job`` (test seam). The
    asyncio tick runs ``run_job`` via ``asyncio.to_thread`` so the
    event loop stays unblocked.
    """

    def __init__(
        self,
        jobs_path: str = DEFAULT_JOBS_PATH,
        run: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        tick_seconds: float = TICK_SECONDS,
    ) -> None:
        self._jobs_path = jobs_path
        self._run = run or subprocess.run
        self._tick_seconds = float(tick_seconds)
        self._jobs: list[_Job] = []
        self._in_flight: set[str] = set()
        self._inflight_lock = threading.Lock()
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def jobs(self) -> list[_Job]:
        return list(self._jobs)

    def load(self) -> None:
        """Load + parse jobs from disk. Raises on JSON / file errors."""
        with open(self._jobs_path) as f:
            data = json.load(f)
        self._jobs = _parse_jobs(data)
        logger.info("[cron] registered %d jobs", len(self._jobs))

    def due_jobs(self, now: datetime | None = None) -> list[_Job]:
        """Return enabled jobs whose schedule/interval is due at *now*.

        Defaults to ``datetime.now(timezone.utc)``. Pure function —
        callers can drive it from tests with a fixed clock.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        out: list[_Job] = []
        now_ts = time.time()
        for job in self._jobs:
            if not job.enabled:
                continue
            with self._inflight_lock:
                if job.id in self._in_flight:
                    continue
            due = False
            if job.schedule is not None:
                due = job.schedule.matches(now)
            elif job.interval_minutes > 0:
                elapsed_min = (now_ts - job.last_run_at) / 60.0
                if job.last_run_at == 0.0 or elapsed_min >= job.interval_minutes:
                    due = True
            if due:
                out.append(job)
        return out

    def run_job(self, job: _Job) -> int:
        """Run *job* synchronously and append the output to log_file.

        Returns the process exit code. Honours ``JOB_TIMEOUT_SECONDS``.
        Single-flight: a second call with the same id while the first
        is running is a no-op (returns 0; logs a warning).
        """
        with self._inflight_lock:
            if job.id in self._in_flight:
                logger.warning("[cron] job %s already running — skipping", job.id)
                return 0
            self._in_flight.add(job.id)
        try:
            return self._run_job_unsafe(job)
        finally:
            with self._inflight_lock:
                self._in_flight.discard(job.id)

    def _run_job_unsafe(self, job: _Job) -> int:
        log_path = job.log_file
        try:
            os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        except OSError as exc:
            logger.error("[cron] cannot mkdir for %s: %s", job.id, exc)
            return 1

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        argv = [job.command, *job.args]
        header = f"[{ts}] + {' '.join(argv)}\n"
        try:
            with open(log_path, "a", encoding="utf-8") as logf:
                logf.write(header)
                logf.flush()
                try:
                    proc = self._run(
                        argv,
                        timeout=JOB_TIMEOUT_SECONDS,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    exit_code = int(proc.returncode)
                    logf.write(proc.stdout or "")
                    logf.write(proc.stderr or "")
                    logf.write(f"[exit {exit_code}]\n")
                except subprocess.TimeoutExpired as exc:
                    logf.write(f"[timeout after {JOB_TIMEOUT_SECONDS}s]\n")
                    logger.error("[cron] job %s timed out", job.id)
                    exit_code = 124
                except FileNotFoundError as exc:
                    logf.write(f"[spawn error: {exc}]\n")
                    logger.error("[cron] job %s spawn error: %s", job.id, exc)
                    exit_code = 127
                except Exception as exc:  # noqa: BLE001
                    logf.write(f"[error: {exc}]\n")
                    logger.exception("[cron] job %s raised", job.id)
                    exit_code = 1
        except OSError as exc:
            logger.error("[cron] cannot open log file %s: %s", log_path, exc)
            exit_code = 1

        job.last_run_at = time.time()
        logger.info("[cron] ran %s (exit %d)", job.id, exit_code)
        return exit_code

    async def _tick_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                due = self.due_jobs()
            except Exception:  # noqa: BLE001
                logger.exception("[cron] due_jobs failed")
                due = []
            for job in due:
                # Run each job on a worker thread; the event loop stays free.
                asyncio.create_task(self._run_job_async(job))
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._tick_seconds,
                )
            except asyncio.TimeoutError:
                continue

    async def _run_job_async(self, job: _Job) -> None:
        try:
            await asyncio.to_thread(self.run_job, job)
        except Exception:  # noqa: BLE001
            logger.exception("[cron] async wrapper for %s crashed", job.id)

    async def start(self) -> None:
        if self._task is not None:
            return
        self.load()
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._tick_loop(), name="hermes_agent.cron",
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._task = None


__all__: tuple[str, ...] = (
    "CronParseError",
    "CronSchedule",
    "CronScheduler",
    "DEFAULT_JOBS_PATH",
    "JOB_TIMEOUT_SECONDS",
    "TICK_SECONDS",
)


# Quiet "unused import" lint without polluting the public surface.
_ = sys