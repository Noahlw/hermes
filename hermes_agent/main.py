"""Hermes V1 gateway entrypoint.

``python -m hermes_agent`` runs the multiplexed runtime (Discord bots +
cron scheduler + MCP HTTP server). ``--check`` runs a non-network smoke
test and exits. ``--mcp-stdio`` runs the MCP server over stdio (for
the mcp inspector / local debugging).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import urllib.error
import urllib.request
from typing import Any

from hermes.profiles.provision import plan_provision

from hermes_agent.config import GatewayConfig
from hermes_agent.cron_scheduler import CronScheduler
from hermes_agent.llm import MiniMaxClient
from hermes_agent.mcp_server import run_http_sync, run_stdio_sync

logger = logging.getLogger("hermes_agent")


# -- check ------------------------------------------------------------------


def _check_honcho(base_url: str, timeout: float = 3.0) -> tuple[bool, str]:
    """Best-effort ``GET {base_url}/health`` reachability check."""
    url = base_url.rstrip("/") + "/health"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read(512).decode("utf-8", errors="replace")
            return status == 200, f"HTTP {status}: {raw.strip()[:120]}"
    except urllib.error.URLError as exc:
        return False, f"unreachable: {exc.reason}"
    except (TimeoutError, OSError) as exc:
        return False, f"error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"error: {exc}"


def _check_profiles(config: GatewayConfig) -> tuple[bool, str]:
    plan = plan_provision(root=config.profiles_root)
    errors = plan.validate()
    if errors:
        return False, "; ".join(errors)
    if not plan.dirs:
        return False, "plan has no directories"
    missing_dirs = [d for d in plan.dirs if not os.path.isdir(d)]
    if missing_dirs:
        # Idempotent apply (write-if-absent) — create the dirs now so
        # the check reflects the on-disk state.
        for d in plan.dirs:
            try:
                os.makedirs(d, exist_ok=True)
            except OSError as exc:
                return False, f"mkdir {d} failed: {exc}"
    return True, f"{len(plan.dirs)} dirs, {len(plan.files)} files"


def _check_jobs(jobs_path: str) -> tuple[bool, str]:
    if not os.path.exists(jobs_path):
        return False, f"missing {jobs_path}"
    try:
        from hermes_agent.cron_scheduler import CronScheduler as _CS

        sched = _CS(jobs_path=jobs_path)
        sched.load()
        return True, f"{len(sched.jobs)} jobs"
    except Exception as exc:  # noqa: BLE001
        return False, f"parse error: {exc}"


def _check_mcp_importable() -> tuple[bool, str]:
    try:
        from hermes_agent.mcp_server import create_mcp_server  # noqa: F401

        return True, "create_mcp_server importable"
    except Exception as exc:  # noqa: BLE001
        return False, f"import error: {exc}"


def run_check(config: GatewayConfig) -> int:
    """Run the ``--check`` smoke. Exit 0 if all OK, 1 if any failure."""
    failures: list[str] = []

    # 1. config valid
    print("[check] config: valid")

    # 2. profiles
    ok, msg = _check_profiles(config)
    print(f"[check] profiles: {'ok' if ok else 'FAIL'} — {msg}")
    if not ok:
        failures.append("profiles")

    # 3. jobs.json
    jobs_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "cron",
        "jobs.json",
    )
    ok, msg = _check_jobs(jobs_path)
    print(f"[check] jobs.json: {'ok' if ok else 'FAIL'} — {msg}")
    if not ok:
        failures.append("jobs.json")

    # 4. honcho reachability (informational; do not fail the check).
    honcho_ok, honcho_msg = _check_honcho(config.honcho_base_url)
    print(f"[check] honcho: {'up' if honcho_ok else 'down'} — {honcho_msg}")

    # 5. MCP tools importable
    ok, msg = _check_mcp_importable()
    print(f"[check] mcp tools: {'ok' if ok else 'FAIL'} — {msg}")
    if not ok:
        failures.append("mcp tools")

    if failures:
        print(f"[check] FAIL: {', '.join(failures)}")
        return 1
    print("[check] OK")
    return 0


# -- provision apply ---------------------------------------------------------


def apply_provision(config: GatewayConfig) -> None:
    """Idempotent apply of ``plan_provision``.

    Directories are ``mkdir -p``'d; files are written only when absent.
    """
    plan = plan_provision(root=config.profiles_root)
    errors = plan.validate()
    if errors:
        raise RuntimeError("plan_provision invalid: " + "; ".join(errors))
    for d in plan.dirs:
        os.makedirs(d, exist_ok=True)
    for rel_path, content in plan.files:
        full = os.path.join(config.profiles_root, rel_path)
        if not os.path.exists(full):
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("[gateway] provisioned %s", full)
    logger.info(
        "[gateway] provision: %d dirs, %d files at %s",
        len(plan.dirs),
        len(plan.files),
        config.profiles_root,
    )


# -- multiplex --------------------------------------------------------------


async def _run_multiplex(config: GatewayConfig) -> None:
    """Run Discord + cron + MCP HTTP concurrently; graceful on signal."""
    from hermes_agent.discord_adapter import DiscordGateway

    llm = MiniMaxClient(api_key=config.minimax_api_key)
    gateway = DiscordGateway(config, llm)
    cron = CronScheduler()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_stop(*_: Any) -> None:
        logger.info("[gateway] signal received — shutting down")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_stop)
        except (NotImplementedError, RuntimeError):
            # Windows / non-main thread; signal handlers are best-effort.
            signal.signal(sig, lambda *_: _signal_stop())

    await cron.start()
    await gateway.start()
    logger.info(
        "[gateway] up — discord=%d cron=%d jobs mcp=%s:%d",
        len(gateway.bots),
        len(cron.jobs),
        config.mcp_bind_host,
        config.mcp_port,
    )

    # Each background runner is a long-lived task. ``stop_event``
    # cancels them all on SIGTERM/SIGINT.
    runners: list[asyncio.Task[Any]] = [
        asyncio.create_task(_hold_until_stop(stop_event), name="discord-hold"),
        asyncio.create_task(_watch_cron(cron, stop_event), name="cron-hold"),
        asyncio.create_task(_run_mcp_http(config, llm, stop_event), name="mcp-http"),
    ]
    try:
        done, _pending = await asyncio.wait(
            runners, return_when=asyncio.FIRST_COMPLETED,
        )
        stop_event.set()
        for task in done:
            exc = task.exception()
            if exc is not None:
                logger.exception("[gateway] background task crashed", exc_info=exc)
    finally:
        stop_event.set()
        await asyncio.gather(
            gateway.close(),
            cron.stop(),
            return_exceptions=True,
        )


async def _hold_until_stop(stop_event: asyncio.Event) -> None:
    """Discord bots block inside ``bot.start``; just wait for shutdown."""
    await stop_event.wait()


async def _watch_cron(cron: CronScheduler, stop_event: asyncio.Event) -> None:
    """Watch the cron tick task; surface exceptions to the multiplex loop."""
    cron_task = cron._task  # noqa: SLF001 — internal but documented
    if cron_task is None:
        await stop_event.wait()
        return
    done, _pending = await asyncio.wait(
        {cron_task, asyncio.create_task(stop_event.wait(), name="stop-wait")},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in done:
        if t is cron_task and not stop_event.is_set():
            exc = t.exception()
            if exc is not None:
                stop_event.set()
                raise exc


async def _run_mcp_http(
    config: GatewayConfig, llm: MiniMaxClient, stop_event: asyncio.Event,
) -> None:
    """Run MCP HTTP in a worker thread; cancel on stop_event."""
    loop = asyncio.get_running_loop()
    http_task = loop.run_in_executor(None, run_http_sync, config, llm)
    stop_wait = asyncio.create_task(stop_event.wait())
    done, _pending = await asyncio.wait(
        {http_task, stop_wait}, return_when=asyncio.FIRST_COMPLETED,
    )
    if not http_task.done():
        http_task.cancel()
    for task in done:
        try:
            task.result()
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


# -- arg parsing / entry ----------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hermes_agent",
        description="Hermes V1 gateway runtime",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Run non-network smoke and exit.",
    )
    parser.add_argument(
        "--mcp-stdio", action="store_true",
        help="Run the MCP server over stdio (debug / inspector).",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        help="Python logging level (default INFO).",
    )
    return parser.parse_args(argv)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    """Module-level entry point."""
    if argv is None:
        argv = sys.argv[1:]
    args = _parse_args(argv)
    _configure_logging(args.log_level)

    try:
        config = GatewayConfig.from_env()
    except ValueError as exc:
        # Fail-fast listing every missing key on one screen.
        print(str(exc), file=sys.stderr)
        return 2

    if args.check:
        return run_check(config)

    if args.mcp_stdio:
        llm = MiniMaxClient(api_key=config.minimax_api_key)
        try:
            run_stdio_sync(config, llm)
        except KeyboardInterrupt:
            return 0
        return 0

    apply_provision(config)
    try:
        asyncio.run(_run_multiplex(config))
    except KeyboardInterrupt:
        return 0
    return 0


__all__: tuple[str, ...] = (
    "apply_provision",
    "main",
    "run_check",
)