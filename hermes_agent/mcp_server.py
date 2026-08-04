"""Hermes coding-agent MCP server.

Six tools, all routed through ``route_mcp_tool`` first. The MCP
response envelope is the V1 contract (CONTEXT.md: MCP response envelope);
markdown is only allowed inside string fields, never as the response
shape. INDEX_UNAVAILABLE is a hard failure per CONTEXT.md: MCP failure
policy.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from typing import Any

from hermes.indexer.config import IndexerConfig, load_config
from hermes.indexer.db import CodebaseIndexDB
from hermes.indexer.mirror import show_file_content
from hermes.personas.adapters import route_mcp_tool

from hermes_agent.config import GatewayConfig
from hermes_agent.llm import MiniMaxClient, strip_think

logger = logging.getLogger("hermes_agent")

# Bounded limits per the design — never let a tool pull the whole
# database or fetch the whole internet.
MAX_LIMIT: int = 50
MAX_WEB_FETCH_BYTES: int = 1 * 1024 * 1024
MAX_WEB_SOURCES: int = 3
MAX_WEB_ROUNDS: int = 2
WEB_FETCH_TIMEOUT: float = 10.0
IMPACT_FANOUT: int = 20
CITATION_CONTEXT_DEFAULT: int = 10


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
    """Build the standard MCP response envelope."""
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


def _gate(tool_name: str, misuse_count: int = 0) -> dict[str, Any]:
    """Run ``route_mcp_tool``; return its envelope as-is (gate decision)."""
    return route_mcp_tool(tool_name, misuse_count=misuse_count)


def _gate_error_envelope(tool_name: str, misuse_count: int = 0) -> dict[str, Any]:
    """Return the gate envelope even when the tool is not in scope.

    ``route_mcp_tool`` already returns the OUT_OF_SCOPE envelope; we
    just normalise it to the ``_envelope`` shape so the MCP tool
    layer can return it as-is via ``isError=True``.
    """
    return _gate(tool_name, misuse_count=misuse_count)


def _index_guard(
    tool_name: str,
    fn: Callable[..., dict[str, Any]],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run an index-backed tool, mapping backend failures to envelopes.

    ``CodebaseIndexDB``/``mirror`` raise (psycopg2 ``OperationalError``,
    ``RuntimeError`` when psycopg2 is missing, file errors) when the
    index is unreachable; LLM failures are already contained to
    ``warnings`` inside the tool bodies, so any exception escaping
    here is index-layer. Surface it as INDEX_UNAVAILABLE instead of a
    generic MCP tool error so consumers can distinguish "index down"
    from "bad request".
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — index layer, see docstring
        logger.warning("[mcp] %s indexer error: %s", tool_name, exc)
        return _envelope(
            tool=tool_name,
            ok=False,
            errors=[
                {
                    "code": "INDEX_UNAVAILABLE",
                    "surface": "mcp",
                    "message": str(exc),
                }
            ],
        )


# -- helpers ------------------------------------------------------------------


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


def _safe_limit(limit: int, default: int = 5, cap: int = MAX_LIMIT) -> int:
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


def _summarise_hits(
    llm: MiniMaxClient,
    query: str,
    hits: list[dict[str, Any]],
    *,
    schema_hint: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Ask MiniMax to write a JSON-shaped summary grounded in *hits*.

    Returns ``(summary_markdown, warnings)``. When MiniMax fails the
    summary is empty and a warning is returned (CONTEXT.md MCP
    failure policy: empty-but-valid is ``ok=True``).
    """
    if not hits:
        return "", []
    bullet_lines = []
    for i, h in enumerate(hits, start=1):
        bullet_lines.append(
            f"[{i}] {h.get('owner_name','?')}@{h.get('commit_sha','?')[:8]} "
            f"{h.get('path','?')}:{h.get('start_line','?')}-{h.get('end_line','?')}\n"
            f"  {h.get('snippet','')}"
        )
    grounded = "\n".join(bullet_lines)
    system = (
        "You write concise, grounded Markdown summaries of codebase "
        "search hits. Output a JSON object with at least "
        "`summary_markdown` (string). Do not invent repositories, "
        "paths, or sources. If the hits do not answer the query, "
        "return an empty string."
    )
    user = (
        f"Query: {query}\n\n"
        f"Hits (use ONLY these; do not invent):\n{grounded}\n\n"
        f"Schema hint: {json.dumps(schema_hint, separators=(',', ':'))}"
    )
    warnings: list[dict[str, Any]] = []
    try:
        raw = llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            json_mode=True,
            temperature=0.2,
            max_tokens=1200,
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            {"code": "LLM_FAILURE", "surface": "mcp", "message": str(exc)},
        )
        return "", warnings
    cleaned = strip_think(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Best-effort: use the cleaned text as the summary if it
        # already looks like prose (model returned prose instead of
        # JSON despite the system prompt).
        return cleaned or "", warnings
    summary = str(parsed.get("summary_markdown", "")).strip()
    return summary, warnings


# -- indexer loading ---------------------------------------------------------


def _load_indexer(config: GatewayConfig) -> tuple[IndexerConfig, CodebaseIndexDB] | None:
    path = config.indexer_config_path
    if not path or not _path_exists(path):
        return None
    try:
        indexer_cfg = load_config(path)
        return indexer_cfg, CodebaseIndexDB(indexer_cfg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[mcp] indexer load failed: %s", exc)
        return None


def _path_exists(path: str) -> bool:
    import os

    return bool(path) and os.path.exists(path)


# -- web fetch helpers -------------------------------------------------------


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


# -- tool implementations ----------------------------------------------------


def _tool_library_search(
    db: CodebaseIndexDB,
    llm: MiniMaxClient,
    *,
    query: str,
    repos: list[str] | None,
    revision: str | None,
    limit: int,
) -> dict[str, Any]:
    """library_search: FTS hits + MiniMax-grounded summary."""
    cap = _safe_limit(limit, default=5, cap=MAX_LIMIT)
    hits = _search_hits(db, query, cap, repos, revision=revision)
    citations = _dedup_citations(_hit_to_citation(h) for h in hits)
    summary, warnings = _summarise_hits(
        llm,
        query,
        hits,
        schema_hint={
            "summary_markdown": "<Markdown summary grounded in hits>",
            "hits": [{"citation": "<citation dict>", "snippet": "<text>", "score": "<float?>"}],
        },
    )
    return _envelope(
        tool="library_search",
        ok=True,
        data={
            "summary_markdown": summary,
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
        warnings=warnings,
        job_persona="librarian",
    )


def _tool_knowledge_catalog(
    db: CodebaseIndexDB,
    *,
    repos: list[str] | None,
) -> dict[str, Any]:
    """knowledge_catalog: per-repo freshness (no MiniMax)."""
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
            age_days = (datetime_utcnow() - last_sync).total_seconds() / 86400.0
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
        job_persona="librarian",
    )


def datetime_utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


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
    """expand_citation: fetch + slice a citation (no MiniMax)."""
    raw = show_file_content(repo, revision, path, indexer_cfg)
    lines = raw.splitlines()
    try:
        s = max(1, int(start_line))
        e = max(s, int(end_line))
    except (TypeError, ValueError):
        return _envelope(
            tool="expand_citation",
            ok=False,
            errors=[
                {
                    "code": "BAD_INPUT",
                    "surface": "mcp",
                    "message": "start_line/end_line must be integers",
                }
            ],
            job_persona="librarian",
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
        job_persona="librarian",
    )


def _tool_impact_map(
    db: CodebaseIndexDB,
    llm: MiniMaxClient,
    *,
    mode: str,
    repo: str | None,
    symbol: str | None,
    path: str | None,
    revision: str | None,
    intent: str | None,
    repos: list[str] | None,
) -> dict[str, Any]:
    """impact_map: seed or intent mode."""
    warnings: list[dict[str, Any]] = []
    seed: dict[str, Any] = {"mode": mode}
    seed_hits: list[dict[str, Any]] = []

    if mode == "seed":
        if not symbol and not path:
            return _envelope(
                tool="impact_map",
                ok=False,
                errors=[
                    {
                        "code": "BAD_INPUT",
                        "surface": "mcp",
                        "message": "seed mode requires symbol or path",
                    }
                ],
                job_persona="librarian",
            )
        query = (symbol or "").strip() or (path or "").strip()
        seed_hits = _search_hits(db, query, 20, [repo] if repo else repos)
        if not seed_hits:
            return _envelope(
                tool="impact_map",
                ok=True,
                data={"seed": seed, "nodes": [], "summary_markdown": ""},
                citations=[],
                warnings=warnings,
                job_persona="librarian",
            )
        seed.update({"symbol": symbol, "path": path, "revision": revision})
    elif mode == "intent":
        if not intent:
            return _envelope(
                tool="impact_map",
                ok=False,
                errors=[
                    {
                        "code": "BAD_INPUT",
                        "surface": "mcp",
                        "message": "intent mode requires intent string",
                    }
                ],
                job_persona="librarian",
            )
        # Bounded intent -> keyword map (json_mode, small hit).
        keywords = _intent_to_keywords(llm, intent)
        if keywords:
            seed["keywords"] = keywords
            for kw in keywords:
                seed_hits.extend(_search_hits(db, kw, 5, repos))
        seed["intent"] = intent
    else:
        return _envelope(
            tool="impact_map",
            ok=False,
            errors=[
                {
                    "code": "BAD_INPUT",
                    "surface": "mcp",
                    "message": f"unknown mode: {mode!r}",
                }
            ],
            job_persona="librarian",
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

    summary, llm_warnings = _summarise_hits(
        llm,
        intent or symbol or path or "impact_map",
        seed_hits,
        schema_hint={
            "summary_markdown": "Optional Markdown summary of the blast radius.",
            "nodes": "[citation, relation, score?]",
        },
    )
    warnings.extend(llm_warnings)
    return _envelope(
        tool="impact_map",
        ok=True,
        data={"seed": seed, "nodes": nodes, "summary_markdown": summary},
        citations=citations,
        warnings=warnings,
        job_persona="librarian",
    )


def _intent_to_keywords(llm: MiniMaxClient, intent: str) -> list[str]:
    """Map a free-form intent string to <=5 keywords via MiniMax (json_mode)."""
    try:
        raw = llm.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You convert a free-form intent into 3-5 concrete "
                        "codebase search keywords. Output a JSON object "
                        "with `keywords` (array of strings). Do not invent "
                        "repositories."
                    ),
                },
                {"role": "user", "content": intent},
            ],
            json_mode=True,
            temperature=0.2,
            max_tokens=200,
        )
        parsed = json.loads(strip_think(raw))
        keywords = parsed.get("keywords", [])
        if not isinstance(keywords, list):
            return []
        return [str(k).strip() for k in keywords if str(k).strip()][:5]
    except Exception:  # noqa: BLE001
        return []


def _tool_session_brief(
    db: CodebaseIndexDB,
    llm: MiniMaxClient,
    *,
    task: str,
    repos: list[str] | None,
    focus: str,
) -> dict[str, Any]:
    """session_brief: deterministic retrieve + MiniMax-graded sections."""
    # Split task into coarse tokens (>=3 chars) for FTS hits.
    terms = [w.strip(" .,;:") for w in re.findall(r"\w+", task) if len(w) >= 3]
    if not terms:
        terms = [task.strip()]
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

    bullets = []
    for i, h in enumerate(deduped, start=1):
        bullets.append(
            f"[{i}] {h.get('owner_name','?')} {h.get('path','?')}:"
            f"{h.get('start_line','?')}-{h.get('end_line','?')}\n  {h.get('snippet','')}"
        )
    system = (
        "You write short, grounded session briefs. Output a JSON "
        "object with `brief_markdown` (string) and `sections` (array of "
        "{title, bullets[]}). Use ONLY the supplied hits — do not invent "
        "paths or sources."
    )
    user = (
        f"Task: {task}\nFocus: {focus}\n\n"
        f"Hits (use ONLY these):\n" + ("\n".join(bullets) if bullets else "(no hits)")
    )
    brief_markdown = ""
    sections: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    try:
        raw = llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            json_mode=True,
            temperature=0.2,
            max_tokens=1200,
        )
        parsed = json.loads(strip_think(raw))
        brief_markdown = str(parsed.get("brief_markdown", "")).strip()
        raw_sections = parsed.get("sections", [])
        if isinstance(raw_sections, list):
            sections = [
                {
                    "title": str(s.get("title", "")),
                    "bullets": [str(b) for b in s.get("bullets", []) if b],
                }
                for s in raw_sections
                if isinstance(s, dict)
            ]
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            {"code": "LLM_FAILURE", "surface": "mcp", "message": str(exc)},
        )

    return _envelope(
        tool="session_brief",
        ok=True,
        data={
            "brief_markdown": brief_markdown,
            "sections": sections,
        },
        citations=citations,
        warnings=warnings,
        job_persona="librarian",
    )


def _tool_conduct_research(
    llm: MiniMaxClient,
    *,
    topic: str,
    sources: list[str] | None,
    depth: str,
) -> dict[str, Any]:
    """conduct_research: fetch + MiniMax fills evidence schema.

    One follow-up round if MiniMax reports gaps (bounded, max
    ``MAX_WEB_ROUNDS`` rounds total).
    """
    warnings: list[dict[str, Any]] = []
    out_sources: list[dict[str, Any]] = []
    seen_uris: set[str] = set()

    initial = _safe_sources(sources)
    rounds_done = 0
    while rounds_done < MAX_WEB_ROUNDS:
        rounds_done += 1
        for url in initial:
            _append_source(out_sources, seen_uris, url, warnings)
        if rounds_done == 1:
            # First round: ask MiniMax to identify gaps.
            gaps = _research_gaps(llm, topic, out_sources)
            if not gaps:
                break
            initial = [g for g in gaps if g not in seen_uris][:MAX_WEB_SOURCES]
            if not initial:
                break
        else:
            break

    # MiniMax fills the evidence schema.
    summary, claims, llm_warnings = _research_synthesize(llm, topic, out_sources)
    warnings.extend(llm_warnings)
    return _envelope(
        tool="conduct_research",
        ok=True,
        data={
            "summary_markdown": summary,
            "claims": claims,
            "sources": out_sources,
        },
        warnings=warnings,
        job_persona="researcher",
    )


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
                "surface": "mcp",
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
            {"code": "WEB_FETCH_FAILED", "surface": "mcp", "message": str(exc), "uri": url},
        )
        return
    except Exception as exc:  # noqa: BLE001
        out.append({"uri": url, "title": None, "excerpt": ""})
        warnings.append(
            {"code": "WEB_FETCH_FAILED", "surface": "mcp", "message": str(exc), "uri": url},
        )
        return
    text = _strip_html(raw)
    excerpt = text[:600]
    out.append({"uri": url, "title": None, "excerpt": excerpt})


def _research_gaps(
    llm: MiniMaxClient, topic: str, sources: list[dict[str, Any]]
) -> list[str]:
    """Ask MiniMax to identify up to 3 source URIs still needed."""
    if not sources:
        return []
    state = "\n".join(f"- {s['uri']}: {s['excerpt'][:200]}" for s in sources)
    try:
        raw = llm.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You identify up to 3 concrete HTTP(S) URIs that "
                        "would close the remaining evidence gaps for a "
                        "research topic. Output JSON with `gaps` "
                        "(array of URIs). If the existing sources suffice, "
                        "return an empty array. Do not invent non-existent "
                        "domains; prefer well-known authoritative ones."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Topic: {topic}\nExisting sources:\n{state}",
                },
            ],
            json_mode=True,
            temperature=0.2,
            max_tokens=300,
        )
        parsed = json.loads(strip_think(raw))
        gaps = parsed.get("gaps", [])
        if not isinstance(gaps, list):
            return []
        return [str(g).strip() for g in gaps if str(g).strip()][:MAX_WEB_SOURCES]
    except Exception:  # noqa: BLE001
        return []


def _research_synthesize(
    llm: MiniMaxClient,
    topic: str,
    sources: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Ask MiniMax to fill the conduct_research evidence schema."""
    src_block = "\n".join(
        f"[{i}] {s['uri']}\n  {s['excerpt'][:600]}" for i, s in enumerate(sources, start=1)
    ) or "(no sources fetched)"
    warnings: list[dict[str, Any]] = []
    try:
        raw = llm.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You write grounded research summaries. Output JSON "
                        "with `summary_markdown` (string), `claims` "
                        "(array of {claim, confidence, sources[]}), and "
                        "`sources` (array of {uri, title?, excerpt?}). "
                        "Use ONLY the supplied sources; do not invent."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Topic: {topic}\nSources:\n{src_block}",
                },
            ],
            json_mode=True,
            temperature=0.2,
            max_tokens=1800,
        )
        parsed = json.loads(strip_think(raw))
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            {"code": "LLM_FAILURE", "surface": "mcp", "message": str(exc)},
        )
        return "", [], warnings
    summary = str(parsed.get("summary_markdown", "")).strip()
    claims_raw = parsed.get("claims", [])
    claims: list[dict[str, Any]] = []
    if isinstance(claims_raw, list):
        for c in claims_raw:
            if not isinstance(c, dict):
                continue
            claims.append(
                {
                    "claim": str(c.get("claim", "")).strip(),
                    "confidence": str(c.get("confidence", "low")),
                    "sources": [str(s) for s in c.get("sources", []) if s],
                }
            )
    return summary, claims, warnings


# -- server factory ----------------------------------------------------------


def create_mcp_server(config: GatewayConfig, llm: MiniMaxClient) -> Any:
    """Construct a FastMCP server named ``hermes`` with six tools."""
    # Lazy import — mcp pulls starlette / uvicorn; defer until the
    # MCP subcommand actually runs.
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name="hermes", instructions=INSTRUCTIONS)

    indexer_pair = _load_indexer(config)
    db = indexer_pair[1] if indexer_pair else None
    indexer_cfg = indexer_pair[0] if indexer_pair else None

    def _require_db(tool_name: str) -> dict[str, Any] | None:
        """Return INDEX_UNAVAILABLE envelope when the indexer is missing."""
        if db is not None:
            return None
        return _envelope(
            tool=tool_name,
            ok=False,
            errors=[
                {
                    "code": "INDEX_UNAVAILABLE",
                    "surface": "mcp",
                    "message": (
                        "codebase index unavailable; check INDEXER_CONFIG_PATH / "
                        "Postgres connection"
                    ),
                }
            ],
        )

    @server.tool(name="library_search")
    def library_search(
        query: str,
        repos: list[str] | None = None,
        revision: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """FTS hits + MiniMax-grounded summary."""
        if (gate := _gate("library_search")) and not gate.get("ok"):
            return gate
        err = _require_db("library_search")
        if err is not None:
            return err
        return _index_guard(
            "library_search",
            _tool_library_search,
            db,  # type: ignore[arg-type]
            llm,
            query=query,
            repos=repos,
            revision=revision,
            limit=limit,
        )

    @server.tool(name="knowledge_catalog")
    def knowledge_catalog(repos: list[str] | None = None) -> dict[str, Any]:
        """Per-repo freshness, no MiniMax."""
        if (gate := _gate("knowledge_catalog")) and not gate.get("ok"):
            return gate
        err = _require_db("knowledge_catalog")
        if err is not None:
            return err
        return _index_guard(  # type: ignore[arg-type]
            "knowledge_catalog",
            _tool_knowledge_catalog,
            db,
            repos=repos,
        )

    @server.tool(name="expand_citation")
    def expand_citation(
        repo: str,
        revision: str,
        path: str,
        start_line: int,
        end_line: int,
        symbol: str | None = None,
        context_lines: int = CITATION_CONTEXT_DEFAULT,
    ) -> dict[str, Any]:
        """Deterministic citation expander (no MiniMax)."""
        if (gate := _gate("expand_citation")) and not gate.get("ok"):
            return gate
        if indexer_cfg is None:
            return _envelope(
                tool="expand_citation",
                ok=False,
                errors=[
                    {
                        "code": "INDEX_UNAVAILABLE",
                        "surface": "mcp",
                        "message": "indexer config unavailable",
                    }
                ],
            )
        return _index_guard(
            "expand_citation",
            _tool_expand_citation,
            indexer_cfg,
            repo=repo,
            revision=revision,
            path=path,
            start_line=start_line,
            end_line=end_line,
            symbol=symbol,
            context_lines=context_lines,
        )

    @server.tool(name="impact_map")
    def impact_map(
        mode: str,
        repo: str | None = None,
        symbol: str | None = None,
        path: str | None = None,
        revision: str | None = None,
        intent: str | None = None,
        repos: list[str] | None = None,
    ) -> dict[str, Any]:
        """Seed or intent blast-radius map."""
        if (gate := _gate("impact_map")) and not gate.get("ok"):
            return gate
        err = _require_db("impact_map")
        if err is not None:
            return err
        return _index_guard(
            "impact_map",
            _tool_impact_map,
            db,  # type: ignore[arg-type]
            llm,
            mode=mode,
            repo=repo,
            symbol=symbol,
            path=path,
            revision=revision,
            intent=intent,
            repos=repos,
        )

    @server.tool(name="session_brief")
    def session_brief(
        task: str,
        repos: list[str] | None = None,
        focus: str = "general",
    ) -> dict[str, Any]:
        """Deterministic retrieve + MiniMax-graded sections."""
        if (gate := _gate("session_brief")) and not gate.get("ok"):
            return gate
        err = _require_db("session_brief")
        if err is not None:
            return err
        return _index_guard(
            "session_brief",
            _tool_session_brief,
            db,  # type: ignore[arg-type]
            llm,
            task=task,
            repos=repos,
            focus=focus,
        )

    @server.tool(name="conduct_research")
    def conduct_research(
        topic: str,
        sources: list[str] | None = None,
        depth: str = "standard",
    ) -> dict[str, Any]:
        """Fetch + MiniMax fills evidence schema (no indexer required)."""
        if (gate := _gate("conduct_research")) and not gate.get("ok"):
            return gate
        return _tool_conduct_research(llm, topic=topic, sources=sources, depth=depth)

    return server


INSTRUCTIONS: str = (
    "Hermes V1 coding-agent MCP server. Information suite only — no plan/execute/push "
    "tools. Every tool routes through the persona contract gate first; out-of-scope "
    "tools return OUT_OF_SCOPE envelopes."
)


async def run_stdio(config: GatewayConfig, llm: MiniMaxClient) -> None:
    """Run the MCP server over stdio (local debugging / mcp inspector)."""
    server = create_mcp_server(config, llm)
    await server.run_stdio_async()


async def run_http(config: GatewayConfig, llm: MiniMaxClient) -> None:
    """Run the MCP server over streamable HTTP on the configured bind."""
    server = create_mcp_server(config, llm)
    server.settings.host = config.mcp_bind_host
    server.settings.port = int(config.mcp_port)
    await server.run_streamable_http_async()


def run_stdio_sync(config: GatewayConfig, llm: MiniMaxClient) -> None:
    """Blocking wrapper for ``run_stdio`` (used by ``__main__`` --mcp-stdio)."""
    asyncio.run(run_stdio(config, llm))


def run_http_sync(config: GatewayConfig, llm: MiniMaxClient) -> None:
    """Blocking wrapper for ``run_http``."""
    asyncio.run(run_http(config, llm))


class HttpServerHandle:
    """Run FastMCP over uvicorn with an external stop signal.

    ``serve`` blocks (call it via ``run_in_executor``); ``stop`` asks
    uvicorn to exit so the executor thread joins promptly on shutdown
    instead of holding the MCP port while the process is supposed to
    be gone. Bind failures surface from ``serve`` for the caller to
    raise.
    """

    def __init__(self, config: GatewayConfig, llm: MiniMaxClient) -> None:
        import uvicorn

        server = create_mcp_server(config, llm)
        self._uvicorn = uvicorn.Server(
            uvicorn.Config(
                server.streamable_http_app(),
                host=config.mcp_bind_host,
                port=config.mcp_port,
                log_level="warning",
            )
        )

    def serve(self) -> None:
        """Block until ``stop`` (or process signal). Raises on bind failure."""
        self._uvicorn.run()

    def stop(self) -> None:
        """Ask uvicorn to exit; safe from any thread."""
        self._uvicorn.should_exit = True


__all__: tuple[str, ...] = (
    "create_mcp_server",
    "HttpServerHandle",
    "run_http",
    "run_stdio",
)