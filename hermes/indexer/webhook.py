from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from hermes.indexer.config import IndexerConfig
from hermes.indexer.db import CodebaseIndexDB
from hermes.indexer.sync import SyncJob
from hermes.indexer.utils import validate_webhook_signature

log = logging.getLogger(__name__)

# In-memory rate limiter state
_rate_limit_buckets: dict[str, list[float]] = {}


def _check_rate_limit(
    key: str, max_per_minute: int
) -> bool:
    """Return True if request should be allowed."""
    now = time.monotonic()
    window = 60.0
    bucket = _rate_limit_buckets.get(key, [])
    # Prune old entries
    bucket = [t for t in bucket if now - t < window]
    if len(bucket) >= max_per_minute:
        _rate_limit_buckets[key] = bucket
        return False
    bucket.append(now)
    _rate_limit_buckets[key] = bucket
    return True


# In-memory job dedup
_recent_jobs: dict[str, float] = {}
_DEDUP_WINDOW = 300  # 5 minutes


def _is_duplicate(
    job_key: str, repo_id: int, ref_name: str, after_sha: str
) -> bool:
    """Check if this (repo_id, ref_name, after_sha) was recently enqueued."""
    dedup_key = f"{repo_id}:{ref_name}:{after_sha}"
    now = time.time()
    # Prune old entries
    stale = [k for k, ts in _recent_jobs.items() if now - ts > _DEDUP_WINDOW]
    for k in stale:
        _recent_jobs.pop(k, None)

    if dedup_key in _recent_jobs:
        return True
    _recent_jobs[dedup_key] = now
    return False


@dataclass(frozen=True)
class WebhookResult:
    """Result of processing a webhook delivery."""

    accepted: bool
    status: int  # HTTP status code
    message: str
    job_key: str | None = None


def process_github_push(
    payload_body: bytes,
    signature_header: str,
    config: IndexerConfig,
) -> WebhookResult:
    """Process a GitHub push webhook delivery.

    Steps:
    1. Rate limit check (by sender IP / key)
    2. HMAC validation
    3. Parse payload
    4. Allowlist check
    5. Dedup check
    6. Enqueue sync (direct call for v0)

    Returns WebhookResult with HTTP status + message.
    """
    # 1. Rate limit (by client IP placeholder)
    if not _check_rate_limit("webhook", config.webhook_rate_limit):
        return WebhookResult(
            accepted=False,
            status=429,
            message="Rate limit exceeded",
        )

    # 2. HMAC validation
    if config.webhook_secret and not validate_webhook_signature(
        payload_body, signature_header, config.webhook_secret
    ):
        return WebhookResult(
            accepted=False,
            status=401,
            message="Invalid signature",
        )

    # 3. Parse payload
    try:
        payload = json.loads(payload_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return WebhookResult(
            accepted=False,
            status=400,
            message="Invalid JSON payload",
        )

    repo_full_name = (payload.get("repository") or {}).get("full_name")
    if not repo_full_name:
        return WebhookResult(
            accepted=False,
            status=400,
            message="Missing repository.full_name",
        )

    ref = payload.get("ref", "")
    before_sha = payload.get("before", "")
    after_sha = payload.get("after", "")

    if not ref or not after_sha:
        return WebhookResult(
            accepted=False,
            status=400,
            message="Missing ref or after SHA",
        )

    # Only process branch/tag pushes
    if not ref.startswith("refs/heads/") and not ref.startswith("refs/tags/"):
        return WebhookResult(
            accepted=False,
            status=200,  # ACK but ignore
            message="Ignored non-branch/tag ref",
        )

    ref_name = ref.split("/", 2)[-1] if len(ref.split("/", 2)) >= 3 else ref

    # 4. Allowlist check
    db = CodebaseIndexDB(config)
    try:
        repo = db.get_repo(repo_full_name)
        if repo is None:
            return WebhookResult(
                accepted=False,
                status=200,  # ACK but ignore non-allowlisted
                message="Repo not in allowlist",
            )
        if repo.status == "revoked":
            return WebhookResult(
                accepted=False,
                status=200,
                message="Repo is revoked, ignoring push",
            )

        # 5. Dedup check
        job_key = (
            f"{repo_full_name}:{ref_name}:{after_sha}"
        )
        if _is_duplicate(job_key, repo.id, ref_name, after_sha):
            return WebhookResult(
                accepted=True,
                status=200,
                message="Duplicate, skipped",
                job_key=job_key,
            )

        # 6. Execute sync directly (v0: synchronous for simplicity;
        #    production would enqueue to a background queue)
        sync = SyncJob(config, db)
        try:
            result = sync.incremental_sync(
                owner_name=repo_full_name,
                ref_name=ref_name,
                after_sha=after_sha,
                before_sha=before_sha or None,
            )
            return WebhookResult(
                accepted=True,
                status=200,
                message=f"Synced: {result.get('status', 'ok')}",
                job_key=job_key,
            )
        finally:
            sync.close()
    finally:
        db.close()


def make_webhook_app(config: IndexerConfig) -> Callable:
    """Create a simple WSGI webhook handler suitable for gunicorn/uwsgi."""
    import json as _json

    def app(
        environ: dict, start_response: Callable
    ) -> list[bytes]:
        path = environ.get("PATH_INFO", "")
        method = environ.get("REQUEST_METHOD", "GET")

        if path != "/webhook/github" or method != "POST":
            start_response(
                "404 Not Found",
                [("Content-Type", "application/json")],
            )
            return [b'{"error":"not found"}']

        # Read body
        try:
            content_length = int(environ.get("CONTENT_LENGTH", "0"))
        except ValueError:
            content_length = 0

        body = environ.get("wsgi.input", b"").read(content_length) if content_length else b""
        sig = environ.get("HTTP_X_HUB_SIGNATURE_256", "")

        result = process_github_push(
            payload_body=body,
            signature_header=sig,
            config=config,
        )

        status_text = {
            200: "200 OK",
            400: "400 Bad Request",
            401: "401 Unauthorized",
            429: "429 Too Many Requests",
        }.get(result.status, "500 Internal Server Error")

        response_body = _json.dumps(
            {"accepted": result.accepted, "message": result.message}
        ).encode("utf-8")

        start_response(
            status_text,
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(response_body))),
            ],
        )
        return [response_body]

    return app
