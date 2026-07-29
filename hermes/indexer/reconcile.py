from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from hermes.indexer.config import IndexerConfig
from hermes.indexer.db import CodebaseIndexDB
from hermes.indexer.sync import SyncJob

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconcileResult:
    repos_checked: int
    repos_repaired: int
    errors: list[str]


def run_reconcile(config: IndexerConfig) -> ReconcileResult:
    """Run a single reconcile pass across all active repos.

    Ticket #59: Periodic reconciler compares catalog SHAs against
    current tracked refs and repairs missed webhooks, force-pushes,
    truncated payloads, deleted refs, and manual drift.
    """
    db = CodebaseIndexDB(config)
    sync = SyncJob(config, db)

    try:
        active = db.list_active_repos()
        errors: list[str] = []
        repaired = 0

        for repo in active:
            try:
                results = sync.reconcile_refs(repo.owner_name)
                for r in results:
                    if r.get("action") == "repaired":
                        repaired += 1
            except (RuntimeError, OSError, ValueError) as exc:
                errors.append(f"{repo.owner_name}: {exc}")

        return ReconcileResult(
            repos_checked=len(active),
            repos_repaired=repaired,
            errors=errors,
        )
    finally:
        sync.close()
        db.close()


def reconcile_loop(
    config: IndexerConfig,
    run_once: bool = False,
) -> None:
    """Run reconcile periodically or once.

    For production: run as a cron job or systemd timer on the VM.
    """
    interval = config.reconcile_interval_minutes

    if run_once:
        result = run_reconcile(config)
        log.info(
            "Reconcile: %d checked, %d repaired, %d errors",
            result.repos_checked,
            result.repos_repaired,
            len(result.errors),
        )
        return

    log.info("Starting reconcile loop every %d minutes", interval)
    while True:
        try:
            result = run_reconcile(config)
            log.info(
                "Reconcile pass: %d checked, %d repaired, %d errors",
                result.repos_checked,
                result.repos_repaired,
                len(result.errors),
            )
        except (RuntimeError, OSError, ValueError) as exc:
            log.error("Reconcile loop error: %s", exc)

        time.sleep(interval * 60)
