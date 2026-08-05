#!/usr/bin/env python3
"""Provision Honcho workspaces + peers for the five V1 persona profiles.

Idempotent by contract: Honcho's ``get_or_create_*`` endpoints return the
existing resource when it already exists, so re-runs are safe. Exits
non-zero if any call fails, so it can gate install acceptance.

Usage:
    python3 setup/honcho-workspaces.py [--base-url URL] [--personas p1,p2,...]

Defaults: base URL http://127.0.0.1:8000; personas from
hermes.profiles.config.PROFILE_DEFINITIONS.

Contract (Honcho v3.0.12, self-hosted per ADR 0005 reboot, D-A 2026-08-04):

    POST /v3/workspaces            {"name": <workspace>}   (get-or-create)
    POST /v3/workspaces/<ws>/peers {"name": <peer>}        (PeerCreate, alias id)

Workspace and peer names follow hermes.profiles.config.generate_honcho_json:
``hermes_<persona_id>`` for both — this keeps the repo's honcho.json
contract and the backend state in lockstep (map #76 Task 4).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hermes.profiles.config import PROFILE_DEFINITIONS  # noqa: E402

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def _request(base: str, path: str, payload: dict[str, str]) -> dict:
    """POST *payload* to *base* + *path*; return parsed JSON or raise."""
    req = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:300]
        raise RuntimeError(f"POST {path} -> HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"POST {path} unreachable: {exc.reason}") from exc


def provision(base_url: str, persona_ids: list[str]) -> list[dict[str, str]]:
    """Upsert one workspace + one peer per persona; return the records."""
    created: list[dict[str, str]] = []
    for pid in persona_ids:
        name = f"hermes_{pid}"
        ws = _request(base_url, "/v3/workspaces", {"name": name})
        peer = _request(base_url, f"/v3/workspaces/{name}/peers", {"name": name})
        created.append(
            {
                "persona": pid,
                "workspace": ws.get("name", name),
                "peer": peer.get("name") or peer.get("id", name),
            }
        )
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--personas",
        default=",".join(sorted(PROFILE_DEFINITIONS)),
        help="comma-separated persona ids (default: all V1 profiles)",
    )
    args = parser.parse_args()

    personas = [p.strip() for p in args.personas.split(",") if p.strip()]
    missing = [p for p in personas if p not in PROFILE_DEFINITIONS]
    if missing:
        print(f"[honcho-workspaces] unknown personas: {missing}", file=sys.stderr)
        return 2

    try:
        records = provision(args.base_url, personas)
    except RuntimeError as exc:
        print(f"[honcho-workspaces] FAILED: {exc}", file=sys.stderr)
        return 1

    for r in records:
        print(
            f"[honcho-workspaces] ok {r['persona']}: "
            f"workspace={r['workspace']} peer={r['peer']}"
        )
    print(f"[honcho-workspaces] {len(records)} profiles provisioned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
