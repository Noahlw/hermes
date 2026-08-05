"""Data-only codebase-knowledge tools ported from the archived MCP server.

The six knowledge tools previously lived in
``archive/hermes_agent/mcp_server.py``. This module is the port: each
tool is a pure, JSON-serializable function over the codebase index
(``CodebaseIndexDB`` FTS on ``codebase_index``, ``mirror.show_file_content``
for citation expansion) with the SAME query semantics and citation fields
as the archived versions.

Archived dependencies dropped:
- ``hermes_agent.llm.MiniMaxClient`` / ``strip_think`` — every LLM
  grounding call (``_summarise_hits``, ``_intent_to_keywords``,
  ``_research_gaps``, ``_research_synthesize``) is removed. The tool that
  used it now returns the deterministic data (hits, citations, fetched
  sources) and leaves the narrated ``brief_markdown`` / ``summary_markdown``
  fields empty — the agent's own model grounds and narrates from the
  returned citations.
- ``hermes_agent.config.GatewayConfig`` — the DB/config is created from
  :mod:`hermes.indexer.config` (``~/.config/hermes-indexer/config.json``)
  instead of the archived gateway's ``indexer_config_path``.

Public handlers (``library_search``, ``knowledge_catalog``,
``expand_citation``, ``impact_map``, ``session_brief``,
``conduct_research``) are safe to register as native plugin tools; they
lazily load the index and return the MCP response envelope with
``citations``. The ``TOOL_<NAME>_SCHEMA`` dicts are JSON Schema inputs for
registration; ``TOOLS`` maps each name to its schema / description /
handler.
"""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from hermes.indexer.config import (
    IndexerConfig,
    default_config_path,
    load_config,
)
from hermes.indexer.db import CodebaseIndexDB
from hermes.indexer.mirror import show_file_content

logger = logging.getLogger("hermes.indexer.tools")

# Bounded limits per the design — never let a tool pull the whole
# database or fetch the whole internet (ported unchanged from the
# archived MCP server).
MAX_LIMIT: int = 50
MAX_WEB_FETCH_BYTES: int = 1 * 1024 * 1024
MAX_WEB_SOURCES: int = 3
WEB_FETCH_TIMEOUT: float = 10.0
IMPACT_FANOUT: int = 20
CITATION_CONTEXT_DEFAULT: int = 10

# Persona attributed to each knowledge tool's envelope (unchanged from the
# archived MCP server).
LIBRARIAN_PERSONA: str = "librarian"
RESEARCHER_PERSONA: str = "researcher"


# -- response envelope ------------------------------------------------------


def _envelope(
    *,
    tool: str,
    ok: bool,
    data: dict[str, Any] | None = None,
    citations: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
    job_persona: str | None = None,
) -> dict[str, Any]:
    """Build the standard MCP response envelope (V1 contract)."""
    env: dict[str, Any] = {
        "ok": bool(ok),
        "tool": tool,
        "data": data if data is not None else {},
        "warnings": warnings if warnings is not None else [],
        "errors": errors if errors is not None else [],
    }
    if job_persona is not None:
        env["job_persona"] = job_persona
    if citations is not None:
        env["citations"] = citations
    return env


# -- citation helpers -------------------------------------------------------


def _citation(
    *,
    repo: str,
    revision: str,
    path: str,
    start_line: int,
    end_line: int,
    symbol: str | None = None,
) -> dict[str, Any]:
    cite: dict[str, Any] = {
        "repo": repo,
        "revision": revision,
        "path": path,
        "start_line": int(start_line),
        "end_line": int(end_line),
    }
    if symbol:
        cite["symbol"] = symbol
    return cite


def _dedup_citations(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for c in items:
        key = (
            c.get("repo"),
            c.get("revision"),
            c.get("path"),
            c.get("start_line"),
            c.get("end_line"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _safe_limit(limit: int | None, default: int = 5, cap: int = MAX_LIMIT) -> int:
    if limit is None:
        return default
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return default
    if n <= 0:
        return default
    return min(n, cap)


def _search_hits(
    db: CodebaseIndexDB,
    query: str,
    limit: int,
    repos: list[str] | None,
    revision: str | None = None,
) -> list[dict[str, Any]]:
    """FTS hits with optional repo and revision (commit-sha prefix) filters."""
    hits = db.search_chunks(query, limit=limit)
    if repos:
        wanted = {r.strip() for r in repos if r and r.strip()}
        hits = [h for h in hits if h.get("owner_name") in wanted]
    if revision:
        rev = str(revision).strip()
        hits = [
            h for h in hits
            if str(h.get("commit_sha", "")).startswith(rev)
        ]
    return hits


def _hit_to_citation(hit: dict[str, Any]) -> dict[str, Any]:
    return _citation(
        repo=str(hit.get("owner_name", "")),
        revision=str(hit.get("commit_sha", "")),
        path=str(hit.get("path", "")),
        start_line=int(hit.get("start_line", 0) or 0),
        end_line=int(hit.get("end_line", 0) or 0),
    )


def _intent_to_keywords(intent: str) -> list[str]:
    """Deterministic intent -> keyword fallback (replaces the archived MiniMax call).

    The archived ``_intent_to_keywords`` delegated keyword extraction to
    the LLM. Data-only port tokenizes the intent into up to 5 coarse
    tokens (>= 3 chars) — same ceiling, no model call.
    """
    terms = [w.strip(" .,;:") for w in re.findall(r"\w+", intent) if len(w) >= 3]
    return terms[:5]


def _task_terms(task: str) -> list[str]:
    """Coarse task tokens (>= 3 chars) for FTS (validated by archived session_brief)."""
    terms = [w.strip(" .,;:") for w in re.findall(r"\w+", task) if len(w) >= 3]
    if not terms:
        terms = [task.strip()]
    return terms[:6]


# -- indexer loading --------------------------------------------------------


def _load_config() -> IndexerConfig:
    return load_config(default_config_path())


def _load_db(config: IndexerConfig | None = None) -> CodebaseIndexDB:
    return CodebaseIndexDB(config or _load_config())


def _index_unavailable(tool_name: str, exc: Exception) -> dict[str, Any]:
    logger.warning("[tools] %s indexer error: %s", tool_name, exc)
    return _envelope(
        tool=tool_name,
        ok=False,
        errors=[
            {
                "code": "INDEX_UNAVAILABLE",
                "surface": "plugin",
                "message": str(exc),
            }
        ],
    )


def _bad_input(tool_name: str, message: str) -> dict[str, Any]:
    return _envelope(
        tool=tool_name,
        ok=False,
        errors=[{"code": "BAD_INPUT", "surface": "plugin", "message": message}],
    )


def _index_guard(
    tool_name: str,
    fn: Callable[..., dict[str, Any]],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run an index-backed tool, mapping backend failures to an envelope."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — index layer, see docstring
        return _index_unavailable(tool_name, exc)


def _with_db(tool_name: str, fn: Callable[..., dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    """Load the index DB, then run *fn* under the index guard."""
    try:
        db = _load_db()
    except Exception as exc:  # noqa: BLE001
        return _index_unavailable(tool_name, exc)
    return _index_guard(tool_name, fn, db, **kwargs)


def _with_config(tool_name: str, fn: Callable[..., dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    """Load the indexer config, then run *fn* under the index guard."""
    try:
        cfg = _load_config()
    except Exception as exc:  # noqa: BLE001
        return _index_unavailable(tool_name, exc)
    return _index_guard(tool_name, fn, cfg, **kwargs)


# -- web fetch helpers (conduct_research) -----------------------------------


def _fetch_url(url: str, *, timeout: float = WEB_FETCH_TIMEOUT) -> str:
    """Fetch *url* (http/https only) and return up to 1 MiB of text."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {parsed.scheme}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "hermes-agent/0.1 (+conduct_research)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(MAX_WEB_FETCH_BYTES + 1, )
    if len(raw) > MAX_WEB_FETCH_BYTES:
        raw = raw[:MAX_WEB_FETCH_BYTES]
    return raw.decode("utf-8", errors="replace")


def _strip_html(text: str) -> str:
    # Ponytail: regex strip only — proper HTML parsing is overkill for
    # an excerpt that the model summarises anyway.
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _safe_sources(sources: list[str] | None) -> list[str]:
    if not sources:
        return []
    return [s for s in sources if s][:MAX_WEB_SOURCES]


def _append_source(
    out: list[dict[str, Any]],
    seen: set[str],
    url: str,
    warnings: list[dict[str, Any]],
) -> None:
    if not url or url in seen:
        return
    seen.add(url)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        out.append({"uri": url, "title": None, "excerpt": ""})
        warnings.append(
            {
                "code": "WEB_FETCH_UNSUPPORTED",
                "surface": "plugin",
                "message": f"unsupported scheme: {parsed.scheme}",
                "uri": url,
            }
        )
        return
    try:
        raw = _fetch_url(url)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        out.append({"uri": url, "title": None, "excerpt": ""})
        warnings.append(
            {"code": "WEB_FETCH_FAILED", "surface": "plugin", "message": str(exc), "uri": url},
        )
        return
    except Exception as exc:  # noqa: BLE001
        out.append({"uri": url, "title": None, "excerpt": ""})
        warnings.append(
            {"code": "WEB_FETCH_FAILED", "surface": "plugin", "message": str(exc), "uri": url},
        )
        return
    text = _strip_html(raw)
    excerpt = text[:600]
    out.append({"uri": url, "title": None, "excerpt": excerpt})


# -- tool implementations (data-only) ---------------------------------------


def _tool_library_search(
    db: CodebaseIndexDB,
    *,
    query: str,
    repos: list[str] | None,
    revision: str | None,
    limit: int,
) -> dict[str, Any]:
    """library_search: FTS hits (+ citations). No LLM summary — model narrates."""
    cap = _safe_limit(limit, default=5, cap=MAX_LIMIT)
    hits = _search_hits(db, query, cap, repos, revision=revision)
    citations = _dedup_citations(_hit_to_citation(h) for h in hits)
    return _envelope(
        tool="library_search",
        ok=True,
        data={
            # Dropped MiniMax grounding: the agent's own model narrates
            # from the hits/citations below.
            "summary_markdown": "",
            "hits": [
                {
                    "citation": _hit_to_citation(h),
                    "snippet": h.get("snippet", ""),
                    "score": None,
                }
                for h in hits
            ],
        },
        citations=citations,
        job_persona=LIBRARIAN_PERSONA,
    )


def _tool_knowledge_catalog(
    db: CodebaseIndexDB,
    *,
    repos: list[str] | None,
) -> dict[str, Any]:
    """knowledge_catalog: per-repo freshness (no MiniMax in the archived version)."""
    rows = db.list_active_repos()
    if repos:
        wanted = {r.strip() for r in repos if r and r.strip()}
        rows = [r for r in rows if r.owner_name in wanted]
    out_repos: list[dict[str, Any]] = []
    for row in rows:
        cursor = db.get_cursor(row.id, "refs/heads/" + row.default_branch)
        sha = cursor.last_after_sha if cursor else None
        last_sync = cursor.last_success_at if cursor else None
        stale = False
        if last_sync is not None:
            age_days = (datetime.now(UTC) - last_sync).total_seconds() / 86400.0
            stale = age_days > 30.0
        out_repos.append(
            {
                "owner_name": row.owner_name,
                "default_branch": row.default_branch,
                "last_sync_at": last_sync.isoformat() if last_sync else None,
                "sync_sha": sha,
                "status": row.status,
                "stale": stale,
            }
        )
    return _envelope(
        tool="knowledge_catalog",
        ok=True,
        data={"repos": out_repos},
        job_persona=LIBRARIAN_PERSONA,
    )


def _tool_expand_citation(
    indexer_cfg: IndexerConfig,
    *,
    repo: str,
    revision: str,
    path: str,
    start_line: int,
    end_line: int,
    symbol: str | None,
    context_lines: int,
) -> dict[str, Any]:
    """expand_citation: fetch + slice a citation (no MiniMax in archived version)."""
    raw = show_file_content(repo, revision, path, indexer_cfg)
    lines = raw.splitlines()
    try:
        s = max(1, int(start_line))
        e = max(s, int(end_line))
    except (TypeError, ValueError):
        return _bad_input(
            "expand_citation",
            "start_line/end_line must be integers",
        )
    window = max(0, int(context_lines))
    s_w = max(1, s - window)
    e_w = min(len(lines), e + window)
    snippet = "\n".join(lines[s_w - 1 : e_w])
    return _envelope(
        tool="expand_citation",
        ok=True,
        data={
            "repo": repo,
            "revision": revision,
            "path": path,
            "start_line": s,
            "end_line": e,
            "content": snippet,
        },
        citations=[
            _citation(
                repo=repo,
                revision=revision,
                path=path,
                start_line=s_w,
                end_line=e_w,
                symbol=symbol,
            )
        ],
        job_persona=LIBRARIAN_PERSONA,
    )


def _tool_impact_map(
    db: CodebaseIndexDB,
    *,
    mode: str,
    repo: str | None,
    symbol: str | None,
    path: str | None,
    revision: str | None,
    intent: str | None,
    repos: list[str] | None,
) -> dict[str, Any]:
    """impact_map: seed or intent mode (data-only fan-out)."""
    seed: dict[str, Any] = {"mode": mode}
    seed_hits: list[dict[str, Any]] = []

    if mode == "seed":
        if not symbol and not path:
            return _bad_input(
                "impact_map",
                "seed mode requires symbol or path",
            )
        query = (symbol or "").strip() or (path or "").strip()
        seed_hits = _search_hits(db, query, 20, [repo] if repo else repos)
        if not seed_hits:
            return _envelope(
                tool="impact_map",
                ok=True,
                data={"seed": seed, "nodes": [], "summary_markdown": ""},
                citations=[],
                job_persona=LIBRARIAN_PERSONA,
            )
        seed.update({"symbol": symbol, "path": path, "revision": revision})
    elif mode == "intent":
        if not intent:
            return _bad_input(
                "impact_map",
                "intent mode requires intent string",
            )
        # Bounded intent -> keyword map (deterministic, replaces MiniMax).
        keywords = _intent_to_keywords(intent)
        if keywords:
            seed["keywords"] = keywords
            for kw in keywords:
                seed_hits.extend(_search_hits(db, kw, 5, repos))
        seed["intent"] = intent
    else:
        return _bad_input(
            "impact_map",
            f"unknown mode: {mode!r}",
        )

    # Deterministic fan-out: collect top N distinct (path, sha) tuples
    # sharing the seed symbol/path keyword.
    nodes: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    seen_keys: set[tuple[Any, ...]] = set()
    for h in seed_hits[:IMPACT_FANOUT]:
        cite = _hit_to_citation(h)
        key = (cite["repo"], cite["path"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        relation = (
            "shares_symbol" if symbol and symbol in (h.get("snippet", "") or "") else "co_occurs"
        )
        nodes.append({"citation": cite, "relation": relation, "score": None})
        citations.append(cite)

    return _envelope(
        tool="impact_map",
        ok=True,
        data={
            "seed": seed,
            "nodes": nodes,
            # Dropped MiniMax grounding — the agent narrates the blast radius.
            "summary_markdown": "",
        },
        citations=citations,
        job_persona=LIBRARIAN_PERSONA,
    )


def _tool_session_brief(
    db: CodebaseIndexDB,
    *,
    task: str,
    repos: list[str] | None,
    focus: str,
) -> dict[str, Any]:
    """session_brief: deterministic retrieve (+ citations). LLM sections dropped."""
    # Split task into coarse tokens (>=3 chars) for FTS hits.
    terms = _task_terms(task)
    hits: list[dict[str, Any]] = []
    for term in terms[:6]:
        hits.extend(_search_hits(db, term, 5, repos))
    # Dedupe by (repo,path,start_line,end_line).
    seen: set[tuple[Any, ...]] = set()
    deduped: list[dict[str, Any]] = []
    for h in hits:
        cite = _hit_to_citation(h)
        key = (cite["repo"], cite["path"], cite["start_line"], cite["end_line"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(h)
    citations = _dedup_citations(_hit_to_citation(h) for h in deduped)

    return _envelope(
        tool="session_brief",
        ok=True,
        data={
            # Dropped MiniMax-graded sections: the agent narrates from
            # the cited hits below.
            "brief_markdown": "",
            "sections": [],
        },
        citations=citations,
        job_persona=LIBRARIAN_PERSONA,
    )


def _tool_conduct_research(
    *,
    topic: str,
    sources: list[str] | None,
    depth: str,
) -> dict[str, Any]:
    """conduct_research: fetch sources (data-only). LLM evidence schema dropped."""
    warnings: list[dict[str, Any]] = []
    out_sources: list[dict[str, Any]] = []
    seen_uris: set[str] = set()

    # Single pass over the caller-supplied sources (the archived LLM
    # gap-follow-up round is dropped).
    for url in _safe_sources(sources):
        _append_source(out_sources, seen_uris, url, warnings)

    return _envelope(
        tool="conduct_research",
        ok=True,
        data={
            # Dropped MiniMax synthesis / claims — the agent's own model
            # narrates from the fetched source excerpts.
            "summary_markdown": "",
            "claims": [],
            "sources": out_sources,
        },
        warnings=warnings,
        job_persona=RESEARCHER_PERSONA,
    )


# -- public handlers (native-tool registration surface) ---------------------


def library_search(
    query: str,
    repos: list[str] | None = None,
    revision: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """FTS search over the codebase index; returns hits + citations."""
    return _with_db(
        "library_search",
        _tool_library_search,
        query=query,
        repos=repos,
        revision=revision,
        limit=limit,
    )


def knowledge_catalog(repos: list[str] | None = None) -> dict[str, Any]:
    """Per-repo freshness, no LLM."""
    return _with_db("knowledge_catalog", _tool_knowledge_catalog, repos=repos)


def expand_citation(
    repo: str,
    revision: str,
    path: str,
    start_line: int,
    end_line: int,
    symbol: str | None = None,
    context_lines: int = CITATION_CONTEXT_DEFAULT,
) -> dict[str, Any]:
    """Deterministic citation expander (no LLM)."""
    return _with_config(
        "expand_citation",
        _tool_expand_citation,
        repo=repo,
        revision=revision,
        path=path,
        start_line=start_line,
        end_line=end_line,
        symbol=symbol,
        context_lines=context_lines,
    )


def impact_map(
    mode: str,
    repo: str | None = None,
    symbol: str | None = None,
    path: str | None = None,
    revision: str | None = None,
    intent: str | None = None,
    repos: list[str] | None = None,
) -> dict[str, Any]:
    """Seed or intent blast-radius map (data-only fan-out)."""
    return _with_db(
        "impact_map",
        _tool_impact_map,
        mode=mode,
        repo=repo,
        symbol=symbol,
        path=path,
        revision=revision,
        intent=intent,
        repos=repos,
    )


def session_brief(
    task: str,
    repos: list[str] | None = None,
    focus: str = "general",
) -> dict[str, Any]:
    """Deterministic retrieve + citations; LLM-graded sections dropped."""
    return _with_db(
        "session_brief",
        _tool_session_brief,
        task=task,
        repos=repos,
        focus=focus,
    )


def conduct_research(
    topic: str,
    sources: list[str] | None = None,
    depth: str = "standard",
) -> dict[str, Any]:
    """Fetch caller-supplied sources (no indexer required, no LLM)."""
    return _tool_conduct_research(topic=topic, sources=sources, depth=depth)


# -- JSON Schema inputs (for native tool registration) ----------------------


TOOL_LIBRARY_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "FTS search query over indexed code."},
        "repos": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional owner/name filters.",
        },
        "revision": {
            "type": "string",
            "description": "Optional commit-sha prefix filter.",
        },
        "limit": {
            "type": "integer",
            "description": "Max hits (capped at 50).",
            "default": 5,
        },
    },
    "required": ["query"],
}

TOOL_KNOWLEDGE_CATALOG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "repos": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional owner/name filters.",
        },
    },
    "required": [],
}

TOOL_EXPAND_CITATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "repo": {"type": "string", "description": "owner/name."},
        "revision": {"type": "string", "description": "commit sha."},
        "path": {"type": "string", "description": "repo-relative file path."},
        "start_line": {"type": "integer", "description": "1-indexed start line."},
        "end_line": {"type": "integer", "description": "1-indexed end line."},
        "symbol": {"type": "string", "description": "Optional symbol name."},
        "context_lines": {
            "type": "integer",
            "description": "Lines of context around the citation.",
            "default": CITATION_CONTEXT_DEFAULT,
        },
    },
    "required": ["repo", "revision", "path", "start_line", "end_line"],
}

TOOL_IMPACT_MAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["seed", "intent"],
            "description": "seed (symbol/path) or intent (free-form).",
        },
        "repo": {"type": "string", "description": "owner/name."},
        "symbol": {"type": "string", "description": "Seed symbol name."},
        "path": {"type": "string", "description": "Seed file path."},
        "revision": {"type": "string", "description": "Commit-sha prefix."},
        "intent": {"type": "string", "description": "Free-form blast-radius intent."},
        "repos": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional owner/name filters.",
        },
    },
    "required": ["mode"],
}

TOOL_SESSION_BRIEF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "task": {"type": "string", "description": "Task to brief."},
        "repos": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional owner/name filters.",
        },
        "focus": {
            "type": "string",
            "description": "Briefing focus.",
            "default": "general",
        },
    },
    "required": ["task"],
}

TOOL_CONDUCT_RESEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "description": "Research topic."},
        "sources": {
            "type": "array",
            "items": {"type": "string"},
            "description": "HTTP(S) source URIs to fetch (max 3).",
        },
        "depth": {
            "type": "string",
            "description": "Research depth.",
            "default": "standard",
        },
    },
    "required": ["topic"],
}


# name -> registration spec for native-tool wiring.
TOOLS: dict[str, dict[str, Any]] = {
    "library_search": {
        "schema": TOOL_LIBRARY_SEARCH_SCHEMA,
        "description": "Full-text search over the indexed codebase; returns hits with citations for the agent to narrate.",
        "handler": library_search,
    },
    "knowledge_catalog": {
        "schema": TOOL_KNOWLEDGE_CATALOG_SCHEMA,
        "description": "Per-repository freshness overview of the codebase index.",
        "handler": knowledge_catalog,
    },
    "expand_citation": {
        "schema": TOOL_EXPAND_CITATION_SCHEMA,
        "description": "Expand a code citation into its source snippet with context.",
        "handler": expand_citation,
    },
    "impact_map": {
        "schema": TOOL_IMPACT_MAP_SCHEMA,
        "description": "Map the blast radius of a symbol/path seed or free-form intent.",
        "handler": impact_map,
    },
    "session_brief": {
        "schema": TOOL_SESSION_BRIEF_SCHEMA,
        "description": "Retrieve cited code context for a task before the agent begins.",
        "handler": session_brief,
    },
    "conduct_research": {
        "schema": TOOL_CONDUCT_RESEARCH_SCHEMA,
        "description": "Fetch caller-supplied HTTP(S) sources and return excerpts with citations.",
        "handler": conduct_research,
    },
}


__all__: tuple[str, ...] = (
    "TOOLS",
    "TOOL_LIBRARY_SEARCH_SCHEMA",
    "TOOL_KNOWLEDGE_CATALOG_SCHEMA",
    "TOOL_EXPAND_CITATION_SCHEMA",
    "TOOL_IMPACT_MAP_SCHEMA",
    "TOOL_SESSION_BRIEF_SCHEMA",
    "TOOL_CONDUCT_RESEARCH_SCHEMA",
    "conduct_research",
    "expand_citation",
    "impact_map",
    "knowledge_catalog",
    "library_search",
    "session_brief",
)