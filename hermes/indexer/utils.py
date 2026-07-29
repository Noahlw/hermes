from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Sequence
from pathlib import Path

from hermes.indexer.config import IndexerConfig

_EXCLUDE_PATTERNS: list[re.Pattern[str]] = []


def _compile_excludes(
    patterns: Sequence[str],
) -> list[re.Pattern[str]]:
    """Convert glob-like exclusion patterns to compiled regexes.

    Rules:
    - ``*`` matches any characters within a path component (not ``/``)
    - ``?`` matches exactly one character (not ``/``)
    - Patterns without glob metacharacters are matched as trailing
      path components (``(^|/)pattern$``)
    - Patterns with glob metacharacters are anchored the same way
      (``(?:^|/)pattern$``) so they still match against a component.
    """
    result: list[re.Pattern[str]] = []
    for pat in patterns:
        try:
            parts: list[str] = []
            i = 0
            has_meta = False
            while i < len(pat):
                ch = pat[i]
                if ch == "*":
                    parts.append("[^/]*")
                    has_meta = True
                elif ch == "?":
                    parts.append("[^/]")
                    has_meta = True
                else:
                    parts.append(re.escape(ch))
                i += 1
            inner = "".join(parts)
            if has_meta:
                regex = f"(?:^|/){inner}$"
            else:
                regex = f"(^|/){inner}$"
            result.append(re.compile(regex))
        except re.error:
            pass
    return result


def is_excluded_path(
    rel_path: str, config: IndexerConfig
) -> bool:
    """Return True if *rel_path* should not be indexed."""
    global _EXCLUDE_PATTERNS
    if not _EXCLUDE_PATTERNS:
        _EXCLUDE_PATTERNS = _compile_excludes(config.excluded_paths)
    for pat in _EXCLUDE_PATTERNS:
        if pat.search(rel_path):
            return True
    return False

def detect_language(path: str) -> str | None:
    """Guess programming language from file extension."""
    ext = Path(path).suffix.lower()
    _LANG_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescriptreact",
        ".jsx": "javascriptreact",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".java": "java",
        ".kt": "kotlin",
        ".swift": "swift",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".vue": "vue",
        ".svelte": "svelte",
        ".css": "css",
        ".scss": "scss",
        ".html": "html",
        ".sql": "sql",
        ".sh": "shellscript",
        ".bash": "shellscript",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".md": "markdown",
        ".dockerfile": "dockerfile",
        "dockerfile": "dockerfile",
    }
    return _LANG_MAP.get(ext)


def content_sha256(content: str | bytes) -> str:
    """Return hex digest of content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def validate_webhook_signature(
    payload_body: bytes,
    signature_header: str,
    secret: str,
) -> bool:
    """Validate X-Hub-Signature-256 HMAC."""
    if not signature_header.startswith("sha256="):
        return False
    expected = signature_header[len("sha256="):].strip()
    computed = hmac.new(
        secret.encode("utf-8"), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, computed)
