from __future__ import annotations

import re
from dataclasses import dataclass

from hermes.indexer.utils import (
    content_sha256,
    detect_language,
)

# Chunk size in lines
_CHUNK_LINE_SIZE = 50
_CHUNK_OVERLAP = 5


@dataclass(frozen=True)
class ExtractedSymbol:
    """One symbol extracted from source."""

    name: str
    kind: str  # 'function', 'class', 'method', 'type', 'const', 'interface'
    start_line: int  # 1-based
    end_line: int
    signature: str | None = None


@dataclass(frozen=True)
class FileChunk:
    """A bounded source chunk from a file."""

    chunk_index: int
    start_line: int
    end_line: int
    content: str
    content_sha: str


@dataclass(frozen=True)
class ParsedFile:
    """Result of parsing a single file."""

    path: str
    language: str | None
    content_sha: str
    symbols: tuple[ExtractedSymbol, ...] = ()
    chunks: tuple[FileChunk, ...] = ()


# --- Language-specific symbol regexes ---

_PYTHON_SYMBOL = re.compile(
    r"^(?:async\s+)?(?:def\s+(?P<name>\w+)|class\s+(?P<cname>\w+))"
    r"\s*(?:\(|:)"
)
_PYTHON_DECORATOR = re.compile(r"^@\w+")


_JS_TS_SYMBOL = re.compile(
    r"^(?:export\s+)?"
    r"(?:"
    r"(?:async\s+)?function\s+(?P<fname>\w+)"
    r"|class\s+(?P<cname>\w+)"
    r"|interface\s+(?P<iname>\w+)"
    r"|type\s+(?P<tname>\w+)\s*="
    r"|const\s+(?P<vname>\w+)\s*(?:[:=]|=\s*(?:async\s+)?\()"
    r"|function\s*\*?\s*(?P<gnname>\w+)"
    r")"
)


_GO_SYMBOL = re.compile(
    r"^(?:func\s+(?:\([^)]*\)\s+)?(?P<fname>\w+)"
    r"|type\s+(?P<tname>\w+)\s+(?:struct|interface|func|map))"
)

_RUST_SYMBOL = re.compile(
    r"^(?:"
    r"(?:pub\s+(?:async\s+)?)?fn\s+(?P<fname>\w+)"
    r"|(?:pub\s+)?(?:struct|enum|trait|union|type)\s+(?P<tname>\w+)"
    r"|(?:pub\s+)?(?:impl)\s+(?P<iname>\w+)"
    r")"
)


def _match_symbol(
    line: str, lang: str | None
) -> tuple[str, str] | None:
    """Return (name, kind) if the line declares a symbol.

    Uses simple regex patterns per language.
    """
    if lang == "python":
        m = _PYTHON_SYMBOL.search(line)
        if m:
            name = m.group("name") or m.group("cname")
            kind = "function" if m.group("name") else "class"
            return (name, kind)
    elif lang in ("javascript", "typescript", "typescriptreact", "javascriptreact"):
        m = _JS_TS_SYMBOL.search(line)
        if m:
            for kind_key, kind_name in [
                ("fname", "function"),
                ("cname", "class"),
                ("iname", "interface"),
                ("tname", "type"),
                ("vname", "const"),
                ("gnname", "function"),
            ]:
                name = m.group(kind_key)
                if name:
                    return (name, kind_name)
    elif lang == "go":
        m = _GO_SYMBOL.search(line)
        if m:
            name = m.group("fname") or m.group("tname")
            kind = "function" if m.group("fname") else "type"
            return (name, kind)
    elif lang == "rust":
        m = _RUST_SYMBOL.search(line)
        if m:
            for kind_key, kind_name in [
                ("fname", "function"),
                ("tname", "type"),
                ("iname", "impl"),
            ]:
                name = m.group(kind_key)
                if name:
                    return (name, kind_name)
    return None


_BRACKET_LANG = ("go", "rust", "c", "cpp", "java", "csharp", "kotlin")


def _extract_symbols_from_lines(
    lines: list[str], lang: str | None
) -> list[ExtractedSymbol]:
    """Extract symbols from source lines with scope tracking."""
    symbols: list[ExtractedSymbol] = []
    i = 0
    brace_depth = 0
    active_symbol: dict | None = None

    while i < len(lines):
        line = lines[i]

        if not active_symbol:
            match = _match_symbol(line, lang)
            if match:
                name, kind = match
                active_symbol = {
                    "name": name,
                    "kind": kind,
                    "start_line": i + 1,
                    "signature": line.strip(),
                }
                # For Python/JS, count indent to find scope
                if lang == "python":
                    active_symbol["indent"] = len(line) - len(line.lstrip())
                    active_symbol["body_started"] = False
                elif lang in ("javascript", "typescript", "typescriptreact", "javascriptreact"):
                    brace_depth = 0
                    if "{" in line:
                        brace_depth += line.count("{") - line.count("}")
                    if brace_depth > 0:
                        active_symbol["brace_depth"] = brace_depth
                elif lang in _BRACKET_LANG:
                    if "{" in line:
                        brace_depth = line.count("{") - line.count("}")
                        active_symbol["brace_depth"] = brace_depth
                else:
                    # Fallback: close after finding next symbol
                    active_symbol["close_next"] = True
        else:
            # Track scope to close symbol
            if lang == "python":
                current_indent = len(line) - len(line.lstrip())
                stripped = line.strip()
                if not stripped or current_indent <= active_symbol.get("indent", 0):
                    if active_symbol["body_started"]:
                        symbols.append(
                            ExtractedSymbol(
                                name=active_symbol["name"],
                                kind=active_symbol["kind"],
                                start_line=active_symbol["start_line"],
                                end_line=i,
                                signature=active_symbol.get("signature"),
                            )
                        )
                        active_symbol = None
                    elif stripped:
                        active_symbol["body_started"] = True
                elif stripped:
                    active_symbol["body_started"] = True
            elif lang in (
                "javascript", "typescript",
                "typescriptreact", "javascriptreact",
            ) or lang in _BRACKET_LANG:
                brace_depth += line.count("{") - line.count("}")
                if brace_depth <= 0:
                    symbols.append(
                        ExtractedSymbol(
                            name=active_symbol["name"],
                            kind=active_symbol["kind"],
                            start_line=active_symbol["start_line"],
                            end_line=i + 1,
                            signature=active_symbol.get("signature"),
                        )
                    )
                    active_symbol = None
            elif active_symbol.get("close_next"):
                symbols.append(
                    ExtractedSymbol(
                        name=active_symbol["name"],
                        kind=active_symbol["kind"],
                        start_line=active_symbol["start_line"],
                        end_line=i + 1,
                        signature=active_symbol.get("signature"),
                    )
                )
                active_symbol = None

        i += 1

    # Close any remaining open symbol
    if active_symbol:
        symbols.append(
            ExtractedSymbol(
                name=active_symbol["name"],
                kind=active_symbol["kind"],
                start_line=active_symbol["start_line"],
                end_line=len(lines),
                signature=active_symbol.get("signature"),
            )
        )

    return symbols


def _chunk_lines(
    lines: list[str],
) -> list[FileChunk]:
    """Split source lines into overlapping chunks."""
    chunks: list[FileChunk] = []
    n = len(lines)
    if n == 0:
        return chunks

    step = _CHUNK_LINE_SIZE - _CHUNK_OVERLAP
    if step <= 0:
        step = _CHUNK_LINE_SIZE // 2

    index = 0
    start = 0
    while start < n:
        end = min(start + _CHUNK_LINE_SIZE, n)
        content = "\n".join(lines[start:end])
        chash = content_sha256(content)
        chunks.append(
            FileChunk(
                chunk_index=index,
                start_line=start + 1,
                end_line=end,
                content=content,
                content_sha=chash,
            )
        )
        index += 1
        start += step

    return chunks


def parse_source(
    content: str, path: str, content_sha: str | None = None
) -> ParsedFile:
    """Parse source content into symbols and chunks."""
    lang = detect_language(path)
    lines = content.splitlines()

    if content_sha is None:
        content_sha = content_sha256(content)

    symbols = tuple(
        _extract_symbols_from_lines(lines, lang)
    )
    chunks = tuple(_chunk_lines(lines))

    return ParsedFile(
        path=path,
        language=lang,
        content_sha=content_sha,
        symbols=symbols,
        chunks=chunks,
    )
