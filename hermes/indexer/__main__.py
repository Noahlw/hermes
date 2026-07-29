#!/usr/bin/env python3
"""Codebase indexer CLI — first-index, sync, reconcile, revoke, report.

Usage:
    indexer first-index <owner/name> [--extra-ref <ref> ...]
    indexer sync <owner/name> [--ref <ref>] [--after <sha>] [--before <sha>]
    indexer reconcile [--loop] [--once]
    indexer revoke <owner/name>
    indexer purge <owner/name>
    indexer purge-expired
    indexer resume <owner/name>
    indexer demote-inactive
    indexer pool-check
    indexer config-validate
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from hermes.indexer.config import (
    IndexerConfig,
    default_config_path,
    load_config,
)
from hermes.indexer.db import CodebaseIndexDB
from hermes.indexer.reconcile import (
    reconcile_loop,
    run_reconcile,
)
from hermes.indexer.sync import SyncJob
from hermes.indexer.webhook import make_webhook_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("indexer")


def _run_webhook(config: IndexerConfig, args: list[str]) -> None:
    """Start the webhook HTTP server."""
    import wsgiref.simple_server

    port = config.webhook_port
    app = make_webhook_app(config)
    server = wsgiref.simple_server.make_server(
        host="0.0.0.0",
        port=port,
        app=app,
    )
    log.info("Starting webhook server on 0.0.0.0:%d", port)
    server.serve_forever()



def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    cmd = args[0]

    # Load config (support INDEXER_CONFIG env var override)
    config_path = (
        Path(os.environ["INDEXER_CONFIG"])
        if "INDEXER_CONFIG" in os.environ
        else default_config_path()
    )
    # Load config now for commands that need it
    config = load_config(config_path)

    if cmd == "config-validate":
        print("Config OK")
        print(f"  Allowlist entries: {len(config.allowlist)}")
        for e in config.allowlist:
            refs = ", ".join(e.extra_refs) if e.extra_refs else "(default only)"
            print(f"    - {e.owner_name} [{refs}]")
        sys.exit(0)

    db = CodebaseIndexDB(config)
    sync = SyncJob(config, db)

    try:
        if cmd == "first-index":
            if len(args) < 2:
                print("Usage: indexer first-index <owner/name> [--extra-ref <ref> ...]")
                sys.exit(1)
            owner_name = args[1]
            extra_refs = []
            i = 2
            while i < len(args):
                if args[i] == "--extra-ref" and i + 1 < len(args):
                    extra_refs.append(args[i + 1])
                    i += 2
                else:
                    i += 1
            result = sync.first_index(owner_name, extra_refs)
            print(json.dumps(result, indent=2, default=str))

        elif cmd == "sync":
            if len(args) < 2:
                print("Usage: indexer sync <owner/name> [--ref <ref>] [--after <sha>] [--before <sha>]")
                sys.exit(1)
            owner_name = args[1]
            ref_name = "refs/heads/main"
            after_sha = None
            before_sha = None
            i = 2
            while i < len(args):
                if args[i] == "--ref" and i + 1 < len(args):
                    ref_name = args[i + 1]
                    i += 2
                elif args[i] == "--after" and i + 1 < len(args):
                    after_sha = args[i + 1]
                    i += 2
                elif args[i] == "--before" and i + 1 < len(args):
                    before_sha = args[i + 1]
                    i += 2
                else:
                    i += 1

            if after_sha:
                result = sync.incremental_sync(
                    owner_name, ref_name, after_sha, before_sha
                )
            else:
                # Resolve current SHA and sync
                from hermes.indexer.mirror import resolve_ref_sha
                sha = resolve_ref_sha(owner_name, ref_name, config)
                result = sync.incremental_sync(
                    owner_name, ref_name, sha, before_sha
                )
            print(json.dumps(result, indent=2, default=str))

        elif cmd == "reconcile":
            loop = "--loop" in args
            if loop:
                reconcile_loop(config, run_once=False)
            else:
                reconcile_result = run_reconcile(config)
                print(json.dumps({
                    "repos_checked": reconcile_result.repos_checked,
                    "repos_repaired": reconcile_result.repos_repaired,
                    "errors": reconcile_result.errors,
                }, indent=2, default=str))

        elif cmd == "revoke":
            if len(args) < 2:
                print("Usage: indexer revoke <owner/name>")
                sys.exit(1)
            result = sync.revoke_repo(args[1])
            print(json.dumps(result, indent=2, default=str))

        elif cmd == "purge":
            if len(args) < 2:
                print("Usage: indexer purge <owner/name>")
                sys.exit(1)
            result = sync.force_purge(args[1])
            print(json.dumps(result, indent=2, default=str))

        elif cmd == "purge-expired":
            results = sync.purge_expired()
            print(json.dumps(results, indent=2, default=str))

        elif cmd == "resume":
            if len(args) < 2:
                print("Usage: indexer resume <owner/name>")
                sys.exit(1)
            result = sync.resume_repo(args[1])
            print(json.dumps(result, indent=2, default=str))

        elif cmd == "demote-inactive":
            results = sync.demote_inactive()
            print(json.dumps(results, indent=2, default=str))

        elif cmd == "pool-check":
            result = sync.check_inactive_pool_size()
            print(json.dumps(result, indent=2, default=str))

        elif cmd == "webhook":
            _run_webhook(config, args)

        else:
            print(f"Unknown command: {cmd}")
            print(__doc__)
            sys.exit(1)

    finally:
        sync.close()


if __name__ == "__main__":
    main()
