"""Unit tests for hermes/indexer/webhook.py.

Exercises HMAC signature validation, in-memory rate limiting, duplicate-job
detection, the full process_github_push flow against a mocked DB + sync layer,
and the WSGI app routing produced by make_webhook_app. No network. No Postgres.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import unittest
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

from hermes.indexer.config import AllowlistEntry, IndexerConfig
from hermes.indexer.webhook import (
    WebhookResult,
    _check_rate_limit,
    _is_duplicate,
    _rate_limit_buckets,
    _recent_jobs,
    make_webhook_app,
    process_github_push,
)

# --- Helpers ----------------------------------------------------------------


def _sign(body: bytes, secret: str) -> str:
    """Return a GitHub-style X-Hub-Signature-256 header value."""
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def _push_payload(
    repo: str = "acme/widgets",
    ref: str = "refs/heads/main",
    before: str = "0" * 40,
    after: str = "1" * 40,
) -> dict[str, Any]:
    return {
        "ref": ref,
        "before": before,
        "after": after,
        "repository": {"full_name": repo},
        "sender": {"login": "octocat"},
    }


def _make_repo_row(
    owner_name: str = "acme/widgets",
    status: str = "active",
    repo_id: int = 42,
) -> Any:
    """Build a RepoRow-like mock that the webhook code can read."""
    row = MagicMock()
    row.id = repo_id
    row.owner_name = owner_name
    row.default_branch = "main"
    row.status = status
    row.revoked_at = None
    row.purge_after = None
    row.created_at = datetime.now(timezone.utc)
    return row


def _make_config(
    *,
    secret: str = "shhh",
    rate_limit: int = 60,
    allowlist: tuple[AllowlistEntry, ...] = (
        AllowlistEntry(owner_name="acme/widgets"),
    ),
) -> IndexerConfig:
    return IndexerConfig(
        allowlist=allowlist,
        webhook_secret=secret,
        webhook_rate_limit=rate_limit,
    )


def _make_sync_result(
    status: str = "synced",
    files_added: int = 1,
    files_modified: int = 0,
    files_deleted: int = 0,
) -> dict[str, Any]:
    return {
        "owner_name": "acme/widgets",
        "repo_id": 42,
        "status": status,
        "files_added": files_added,
        "files_modified": files_modified,
        "files_deleted": files_deleted,
    }


# --- Base test case ---------------------------------------------------------


class WebhookTestCase(unittest.TestCase):
    """Shared setUp: clear module-level rate-limit + dedup state."""

    def setUp(self) -> None:
        _rate_limit_buckets.clear()
        _recent_jobs.clear()
        self.config = _make_config()
        self.repo_row = _make_repo_row()

    def _build_db_context(
        self,
        *,
        repo: Any | None = None,
        sync_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a dict of mock targets suitable for mock.patch.multiple."""
        db = MagicMock()
        db.get_repo.return_value = repo

        sync = MagicMock()
        sync.incremental_sync.return_value = (
            sync_result if sync_result is not None
            else _make_sync_result()
        )

        return {"db_cls": db, "sync_cls": sync, "db": db, "sync": sync}


# --- HMAC signature validation ---------------------------------------------


class HMACSignatureTests(WebhookTestCase):
    """Direct exercise of validate_webhook_signature via process_github_push.

    We mock out everything past the HMAC check (the DB) so we can isolate
    the signature branch by repo allowlist outcome.
    """

    def _signature_check_setup(self, valid_sig: str, body: bytes) -> dict:
        ctx = self._build_db_context(repo=self.repo_row)
        # valid_sig=True means signature matches; we patch signature checking
        # only when we want to bypass it. For these tests we exercise the
        # real validator via real HMAC computation.
        return ctx

    def test_valid_signature_passes(self) -> None:
        body = json.dumps(_push_payload()).encode("utf-8")
        sig = _sign(body, self.config.webhook_secret)
        ctx = self._build_db_context(repo=self.repo_row)
        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ), patch(
            "hermes.indexer.webhook.SyncJob",
            return_value=ctx["sync"],
        ):
            result = process_github_push(body, sig, self.config)
        self.assertEqual(result.status, 200)
        self.assertTrue(result.accepted)
        self.assertTrue(result.message.startswith("Synced:"))

    def test_invalid_signature_returns_401(self) -> None:
        body = json.dumps(_push_payload()).encode("utf-8")
        # Sign with the WRONG secret; header is well-formed but does not match.
        bad_sig = _sign(body, "wrong-secret")
        ctx = self._build_db_context(repo=self.repo_row)
        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ):
            result = process_github_push(body, bad_sig, self.config)
        self.assertEqual(result.status, 401)
        self.assertFalse(result.accepted)
        self.assertEqual(result.message, "Invalid signature")

    def test_missing_signature_header_returns_401(self) -> None:
        body = json.dumps(_push_payload()).encode("utf-8")
        ctx = self._build_db_context(repo=self.repo_row)
        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ):
            result = process_github_push(body, "", self.config)
        self.assertEqual(result.status, 401)
        self.assertFalse(result.accepted)
        self.assertEqual(result.message, "Invalid signature")

    def test_malformed_signature_prefix_returns_401(self) -> None:
        body = json.dumps(_push_payload()).encode("utf-8")
        # Valid hex but missing the "sha256=" prefix that the validator
        # requires.
        raw_hex = hmac.new(
            self.config.webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        ctx = self._build_db_context(repo=self.repo_row)
        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ):
            result = process_github_push(body, raw_hex, self.config)
        self.assertEqual(result.status, 401)

    def test_empty_secret_skips_signature_check(self) -> None:
        # When webhook_secret is empty (not configured), the signature is
        # accepted regardless of what the caller sends. This documents the
        # intentional dev-mode bypass.
        config = _make_config(secret="")
        body = json.dumps(_push_payload()).encode("utf-8")
        ctx = self._build_db_context(repo=self.repo_row)
        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ), patch(
            "hermes.indexer.webhook.SyncJob",
            return_value=ctx["sync"],
        ):
            result = process_github_push(body, "anything", config)
        self.assertEqual(result.status, 200)
        self.assertTrue(result.accepted)


# --- Rate limiting ----------------------------------------------------------


class RateLimitTests(WebhookTestCase):
    def test_allows_requests_within_limit(self) -> None:
        self.assertTrue(_check_rate_limit("webhook", max_per_minute=3))
        self.assertTrue(_check_rate_limit("webhook", max_per_minute=3))
        self.assertTrue(_check_rate_limit("webhook", max_per_minute=3))

    def test_blocks_requests_after_limit(self) -> None:
        for _ in range(3):
            self.assertTrue(_check_rate_limit("webhook", max_per_minute=3))
        # Fourth call in the same window must be blocked.
        self.assertFalse(_check_rate_limit("webhook", max_per_minute=3))

    def test_separate_keys_have_independent_buckets(self) -> None:
        # Fill one bucket; the other should still have capacity.
        for _ in range(2):
            self.assertTrue(_check_rate_limit("k1", max_per_minute=2))
        self.assertFalse(_check_rate_limit("k1", max_per_minute=2))
        # k2 is untouched.
        self.assertTrue(_check_rate_limit("k2", max_per_minute=2))

    def test_process_github_push_returns_429_when_rate_limited(self) -> None:
        # Pre-fill the rate-limit bucket to the cap; next call must 429
        # before any DB work happens.
        ctx = self._build_db_context(repo=self.repo_row)
        config = _make_config(rate_limit=1)
        body = json.dumps(_push_payload()).encode("utf-8")
        sig = _sign(body, config.webhook_secret)

        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ), patch(
            "hermes.indexer.webhook.SyncJob",
            return_value=ctx["sync"],
        ):
            # First call consumes the single permit.
            r1 = process_github_push(body, sig, config)
            # Reset the mock call tracking so we can assert the second
            # (rate-limited) call does not touch the DB.
            ctx["db"].reset_mock()
            ctx["db"].get_repo.return_value = self.repo_row
            # Second call should be 429.
            r2 = process_github_push(body, sig, config)

        self.assertEqual(r1.status, 200)
        self.assertEqual(r2.status, 429)
        self.assertFalse(r2.accepted)
        self.assertEqual(r2.message, "Rate limit exceeded")
        # The rate-limited path must NOT consult the DB.
        ctx["db"].get_repo.assert_not_called()

# --- Duplicate job detection ------------------------------------------------


class DuplicateJobTests(WebhookTestCase):
    def test_same_job_key_is_skipped(self) -> None:
        # First call registers, second is detected as duplicate.
        self.assertFalse(
            _is_duplicate("k", repo_id=1, ref_name="main", after_sha="abc")
        )
        self.assertTrue(
            _is_duplicate("k", repo_id=1, ref_name="main", after_sha="abc")
        )

    def test_different_after_sha_is_not_duplicate(self) -> None:
        self.assertFalse(
            _is_duplicate("k", repo_id=1, ref_name="main", after_sha="abc")
        )
        self.assertFalse(
            _is_duplicate("k", repo_id=1, ref_name="main", after_sha="def")
        )

    def test_different_repo_id_is_not_duplicate(self) -> None:
        self.assertFalse(
            _is_duplicate("k", repo_id=1, ref_name="main", after_sha="abc")
        )
        self.assertFalse(
            _is_duplicate("k", repo_id=2, ref_name="main", after_sha="abc")
        )

    def test_process_github_push_returns_skip_for_duplicate(self) -> None:
        ctx = self._build_db_context(repo=self.repo_row)
        body = json.dumps(_push_payload()).encode("utf-8")
        sig = _sign(body, self.config.webhook_secret)

        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ), patch(
            "hermes.indexer.webhook.SyncJob",
            return_value=ctx["sync"],
        ):
            r1 = process_github_push(body, sig, self.config)
            r2 = process_github_push(body, sig, self.config)

        self.assertEqual(r1.status, 200)
        self.assertEqual(r2.status, 200)
        self.assertTrue(r2.accepted)
        self.assertEqual(r2.message, "Duplicate, skipped")
        # First call drives the sync; the duplicate must NOT.
        ctx["sync"].incremental_sync.assert_called_once()


# --- process_github_push end-to-end (with mocked DB) ------------------------


class ProcessGithubPushTests(WebhookTestCase):
    def test_valid_push_for_allowlisted_repo(self) -> None:
        body = json.dumps(_push_payload()).encode("utf-8")
        sig = _sign(body, self.config.webhook_secret)
        ctx = self._build_db_context(repo=self.repo_row)

        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ), patch(
            "hermes.indexer.webhook.SyncJob",
            return_value=ctx["sync"],
        ):
            result = process_github_push(body, sig, self.config)

        self.assertIsInstance(result, WebhookResult)
        self.assertTrue(result.accepted)
        self.assertEqual(result.status, 200)
        self.assertTrue(result.message.startswith("Synced:"))
        self.assertEqual(
            result.job_key, "acme/widgets:main:" + "1" * 40
        )
        # Sync must be invoked with parsed payload values.
        ctx["sync"].incremental_sync.assert_called_once_with(
            owner_name="acme/widgets",
            ref_name="main",
            after_sha="1" * 40,
            before_sha="0" * 40,
        )
        # DB must be closed even on success.
        ctx["db"].close.assert_called_once()
        ctx["sync"].close.assert_called_once()

    def test_non_allowlisted_repo_is_ignored(self) -> None:
        body = json.dumps(
            _push_payload(repo="stranger/notinlist")
        ).encode("utf-8")
        sig = _sign(body, self.config.webhook_secret)
        ctx = self._build_db_context(repo=None)  # not in catalog

        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ), patch(
            "hermes.indexer.webhook.SyncJob",
            return_value=ctx["sync"],
        ):
            result = process_github_push(body, sig, self.config)

        # ACK but do not sync.
        self.assertEqual(result.status, 200)
        self.assertFalse(result.accepted)
        self.assertEqual(result.message, "Repo not in allowlist")
        ctx["sync"].incremental_sync.assert_not_called()
        ctx["sync"].close.assert_not_called()
        ctx["db"].close.assert_called_once()

    def test_revoked_repo_is_ignored(self) -> None:
        body = json.dumps(_push_payload()).encode("utf-8")
        sig = _sign(body, self.config.webhook_secret)
        revoked = _make_repo_row(status="revoked")
        ctx = self._build_db_context(repo=revoked)

        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ), patch(
            "hermes.indexer.webhook.SyncJob",
            return_value=ctx["sync"],
        ):
            result = process_github_push(body, sig, self.config)

        self.assertEqual(result.status, 200)
        self.assertFalse(result.accepted)
        self.assertIn("revoked", result.message)
    def test_bad_signature_returns_401(self) -> None:
        body = json.dumps(_push_payload()).encode("utf-8")
        bad_sig = _sign(body, "wrong-secret")
        ctx = self._build_db_context(repo=self.repo_row)

        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ):
            result = process_github_push(body, bad_sig, self.config)

        self.assertEqual(result.status, 401)
        self.assertFalse(result.accepted)
        # DB is never created when signature fails — the code returns on
        # line 104 before CodebaseIndexDB() is ever called on line 150.
        ctx["db"].close.assert_not_called()
        ctx["sync"].incremental_sync.assert_not_called()

    def test_invalid_json_returns_400(self) -> None:
        body = b"not json at all"
        sig = _sign(body, self.config.webhook_secret)
        ctx = self._build_db_context(repo=self.repo_row)

        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ):
            result = process_github_push(body, sig, self.config)

        self.assertEqual(result.status, 400)
        self.assertEqual(result.message, "Invalid JSON payload")
        ctx["db"].close.assert_not_called()

    def test_missing_repository_returns_400(self) -> None:
        body = json.dumps({"ref": "refs/heads/main", "after": "abc"}).encode(
            "utf-8"
        )
        sig = _sign(body, self.config.webhook_secret)
        ctx = self._build_db_context(repo=self.repo_row)

        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ):
            result = process_github_push(body, sig, self.config)

        self.assertEqual(result.status, 400)
        self.assertEqual(result.message, "Missing repository.full_name")

    def test_non_branch_ref_is_acknowledged_and_ignored(self) -> None:
        body = json.dumps(
            _push_payload(ref="refs/notes/commits")
        ).encode("utf-8")
        sig = _sign(body, self.config.webhook_secret)
        ctx = self._build_db_context(repo=self.repo_row)

        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ), patch(
            "hermes.indexer.webhook.SyncJob",
            return_value=ctx["sync"],
        ):
            result = process_github_push(body, sig, self.config)

        self.assertEqual(result.status, 200)
        self.assertFalse(result.accepted)
        self.assertIn("Ignored", result.message)
        ctx["sync"].incremental_sync.assert_not_called()

    def test_tag_ref_is_processed(self) -> None:
        body = json.dumps(
            _push_payload(ref="refs/tags/v1.0.0", ref_name_replacement=None)  # type: ignore[arg-type]
        ).encode("utf-8") if False else json.dumps(
            _push_payload(ref="refs/tags/v1.0.0")
        ).encode("utf-8")
        sig = _sign(body, self.config.webhook_secret)
        ctx = self._build_db_context(repo=self.repo_row)

        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ), patch(
            "hermes.indexer.webhook.SyncJob",
            return_value=ctx["sync"],
        ):
            result = process_github_push(body, sig, self.config)

        self.assertEqual(result.status, 200)
        self.assertTrue(result.accepted)
        ctx["sync"].incremental_sync.assert_called_once()
        # ref_name should be "v1.0.0" (the part after refs/tags/).
        _, kwargs = ctx["sync"].incremental_sync.call_args
        self.assertEqual(kwargs["ref_name"], "v1.0.0")

    def test_db_closed_even_when_sync_raises(self) -> None:
        body = json.dumps(_push_payload()).encode("utf-8")
        sig = _sign(body, self.config.webhook_secret)
        ctx = self._build_db_context(repo=self.repo_row)
        ctx["sync"].incremental_sync.side_effect = RuntimeError(
            "boom"
        )

        with patch(
            "hermes.indexer.webhook.CodebaseIndexDB",
            return_value=ctx["db"],
        ), patch(
            "hermes.indexer.webhook.SyncJob",
            return_value=ctx["sync"],
        ), self.assertRaises(RuntimeError):
            process_github_push(body, sig, self.config)

        ctx["db"].close.assert_called_once()
        ctx["sync"].close.assert_called_once()


# --- WSGI app routing -------------------------------------------------------


class WSGIAppRoutingTests(WebhookTestCase):
    """Drive make_webhook_app with synthetic environ dicts.

    We never call process_github_push here for the routing tests because
    those paths return before any business logic. For the happy path we
    mock process_github_push to inspect the environ values it receives.
    """

    def _env(
        self,
        path: str = "/webhook/github",
        method: str = "POST",
        body: bytes = b"",
        signature: str = "",
        content_length: str | None = None,
    ) -> dict[str, Any]:
        wsgi_input = io.BytesIO(body)
        environ: dict[str, Any] = {
            "PATH_INFO": path,
            "REQUEST_METHOD": method,
            "wsgi.input": wsgi_input,
            "HTTP_X_HUB_SIGNATURE_256": signature,
            "CONTENT_LENGTH": (
                content_length if content_length is not None
                else str(len(body))
            ),
        }
        return environ

    def _start_response(self) -> tuple[Callable[[str, list], None], list]:
        calls: list[tuple[str, list]] = []

        def sr(status: str, headers: list) -> None:
            calls.append((status, headers))

        return sr, calls

    def test_wrong_path_returns_404(self) -> None:
        app = make_webhook_app(self.config)
        sr, calls = self._start_response()
        body = app(self._env(path="/something/else"), sr)
        self.assertEqual(calls[0][0], "404 Not Found")
        self.assertEqual(body, [b'{"error":"not found"}'])

    def test_wrong_method_returns_404(self) -> None:
        app = make_webhook_app(self.config)
        sr, calls = self._start_response()
        body = app(self._env(method="GET"), sr)
        self.assertEqual(calls[0][0], "404 Not Found")
        self.assertEqual(body, [b'{"error":"not found"}'])

    def test_correct_path_routes_to_processor(self) -> None:
        app = make_webhook_app(self.config)
        body_bytes = json.dumps(_push_payload()).encode("utf-8")
        sig = _sign(body_bytes, self.config.webhook_secret)

        fake_result = WebhookResult(
            accepted=True, status=200, message="ok", job_key="k"
        )

        with patch(
            "hermes.indexer.webhook.process_github_push",
            return_value=fake_result,
        ) as mock_proc:
            sr, calls = self._start_response()
            response = app(
                self._env(
                    body=body_bytes,
                    signature=sig,
                    content_length=str(len(body_bytes)),
                ),
                sr,
            )

        # Routing succeeded: HTTP 200 returned with JSON body containing
        # the fields from the WebhookResult.
        self.assertEqual(calls[0][0], "200 OK")
        self.assertTrue(
            any(h[0] == "Content-Type" for h in calls[0][1])
        )
        payload = json.loads(response[0].decode("utf-8"))
        self.assertEqual(payload, {"accepted": True, "message": "ok"})
        # The processor must have been invoked with the parsed body bytes
        # and the signature header exactly as they appeared in environ.
        mock_proc.assert_called_once()
        _args, kwargs = mock_proc.call_args
        self.assertEqual(kwargs["payload_body"], body_bytes)
        self.assertEqual(kwargs["signature_header"], sig)
        self.assertIs(kwargs["config"], self.config)

    def test_non_200_status_maps_to_correct_status_text(self) -> None:
        app = make_webhook_app(self.config)
        for code, text in (
            (200, "200 OK"),
            (400, "400 Bad Request"),
            (401, "401 Unauthorized"),
            (429, "429 Too Many Requests"),
        ):
            fake_result = WebhookResult(
                accepted=False, status=code, message="x"
            )
            with patch(
                "hermes.indexer.webhook.process_github_push",
                return_value=fake_result,
            ):
                sr, calls = self._start_response()
                app(self._env(body=b"{}"), sr)
            self.assertEqual(calls[0][0], text, msg=f"status={code}")

    def test_content_length_defaults_to_zero_on_invalid_header(self) -> None:
        # CONTENT_LENGTH that isn't parseable should not crash routing.
        app = make_webhook_app(self.config)
        fake_result = WebhookResult(
            accepted=False, status=400, message="bad"
        )
        with patch(
            "hermes.indexer.webhook.process_github_push",
            return_value=fake_result,
        ) as mock_proc:
            sr, _ = self._start_response()
            env = self._env()
            env["CONTENT_LENGTH"] = "not-a-number"
            env["wsgi.input"] = io.BytesIO(b"hello")
            app(env, sr)
        # Processor receives empty body since CONTENT_LENGTH fell back to 0.
        _args, kwargs = mock_proc.call_args
        self.assertEqual(kwargs["payload_body"], b"")


if __name__ == "__main__":
    unittest.main()