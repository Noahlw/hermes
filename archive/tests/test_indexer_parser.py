"""Tests for the Hermes indexer parser utilities.

Exercises :mod:`hermes.indexer.parser` (symbol extraction and chunking)
and the indexer language / hashing / exclusion helpers from
:mod:`hermes.indexer.utils`. Tests are pure unit tests — no Postgres,
no network, no filesystem I/O.
"""

from __future__ import annotations

import unittest

from hermes.indexer.config import IndexerConfig
from hermes.indexer.parser import (
    ExtractedSymbol,
    FileChunk,
    ParsedFile,
    parse_source,
)
from hermes.indexer.utils import (
    content_sha256,
    detect_language,
    is_excluded_path,
)


def _basic_config() -> IndexerConfig:
    """Minimal valid IndexerConfig for is_excluded_path tests."""
    return IndexerConfig(allowlist=())


class DetectLanguageTests(unittest.TestCase):
    """`detect_language` maps file extensions to language tags."""

    def test_python(self) -> None:
        self.assertEqual(detect_language("foo.py"), "python")

    def test_javascript(self) -> None:
        self.assertEqual(detect_language("foo.js"), "javascript")

    def test_typescript(self) -> None:
        self.assertEqual(detect_language("foo.ts"), "typescript")

    def test_typescriptreact(self) -> None:
        self.assertEqual(detect_language("Foo.tsx"), "typescriptreact")

    def test_javascriptreact(self) -> None:
        self.assertEqual(detect_language("Foo.jsx"), "javascriptreact")

    def test_go(self) -> None:
        self.assertEqual(detect_language("main.go"), "go")

    def test_rust(self) -> None:
        self.assertEqual(detect_language("lib.rs"), "rust")

    def test_ruby(self) -> None:
        self.assertEqual(detect_language("app.rb"), "ruby")

    def test_java(self) -> None:
        self.assertEqual(detect_language("Main.java"), "java")

    def test_unknown_extension_returns_none(self) -> None:
        self.assertIsNone(detect_language("README"))

    def test_unknown_extension_with_dot_returns_none(self) -> None:
        self.assertIsNone(detect_language("data.xyz"))

    def test_extension_is_case_insensitive(self) -> None:
        self.assertEqual(detect_language("Foo.PY"), "python")
        self.assertEqual(detect_language("FOO.Js"), "javascript")


class ParseSourcePythonTests(unittest.TestCase):
    """`parse_source` for Python files extracts functions and classes."""

    def test_extracts_simple_function(self) -> None:
        content = "def greet(name):\n    return f'hi {name}'\n"
        result = parse_source(content, "greet.py")
        self.assertEqual(result.language, "python")
        self.assertEqual(len(result.symbols), 1)
        sym = result.symbols[0]
        self.assertEqual(sym.name, "greet")
        self.assertEqual(sym.kind, "function")
        self.assertEqual(sym.start_line, 1)
        # body ends at line 2
        self.assertEqual(sym.end_line, 2)

    def test_extracts_class(self) -> None:
        content = "class Widget:\n    pass\n"
        result = parse_source(content, "widget.py")
        self.assertEqual(len(result.symbols), 1)
        sym = result.symbols[0]
        self.assertEqual(sym.name, "Widget")
        self.assertEqual(sym.kind, "class")

    def test_extracts_async_function(self) -> None:
        content = "async def fetch(url):\n    return url\n"
        result = parse_source(content, "fetch.py")
        self.assertEqual(len(result.symbols), 1)
        self.assertEqual(result.symbols[0].name, "fetch")
        self.assertEqual(result.symbols[0].kind, "function")

    def test_extracts_multiple_top_level_symbols(self) -> None:
        content = (
            "def alpha():\n"
            "    return 1\n"
            "\n"
            "def beta():\n"
            "    return 2\n"
            "\n"
            "class Gamma:\n"
            "    pass\n"
        )
        result = parse_source(content, "multi.py")
        names = [s.name for s in result.symbols]
        self.assertEqual(names, ["alpha", "beta", "Gamma"])
        kinds = [s.kind for s in result.symbols]
        self.assertEqual(kinds, ["function", "function", "class"])

    def test_function_signature_is_captured(self) -> None:
        content = "def hello(name: str) -> str:\n    return name\n"
        result = parse_source(content, "hello.py")
        self.assertEqual(result.symbols[0].signature, "def hello(name: str) -> str:")


class ParseSourceJavaScriptTests(unittest.TestCase):
    """`parse_source` for JS / TS files extracts function / class / type."""

    def test_extracts_function_declaration(self) -> None:
        content = "function add(a, b) {\n    return a + b;\n}\n"
        result = parse_source(content, "add.js")
        self.assertEqual(result.language, "javascript")
        names = [s.name for s in result.symbols]
        self.assertEqual(names, ["add"])
        self.assertEqual(result.symbols[0].kind, "function")

    def test_extracts_class(self) -> None:
        content = "class Greeter {\n    hi() { return 1; }\n}\n"
        result = parse_source(content, "greeter.js")
        names = [s.name for s in result.symbols]
        self.assertIn("Greeter", names)

    def test_extracts_exported_function(self) -> None:
        content = "export function hello() {\n    return 1;\n}\n"
        result = parse_source(content, "hello.js")
        self.assertEqual(result.symbols[0].name, "hello")

    def test_extracts_arrow_function_const(self) -> None:
        content = "const greet = (name) => name;\n"
        result = parse_source(content, "greet.js")
        self.assertEqual(len(result.symbols), 1)
        self.assertEqual(result.symbols[0].name, "greet")
        self.assertEqual(result.symbols[0].kind, "const")

    def test_extracts_typescript_interface(self) -> None:
        content = "interface Point {\n    x: number;\n    y: number;\n}\n"
        result = parse_source(content, "point.ts")
        self.assertEqual(result.language, "typescript")
        self.assertTrue(any(s.name == "Point" for s in result.symbols))

    def test_extracts_typescript_type_alias(self) -> None:
        content = "type ID = string;\n"
        result = parse_source(content, "id.ts")
        self.assertTrue(any(s.name == "ID" for s in result.symbols))


class ScopeTrackingTests(unittest.TestCase):
    """Symbol extraction tracks scope and assigns correct end_line."""

    def test_python_function_end_line_is_last_body_line(self) -> None:
        content = (
            "def add(a, b):\n"
            "    total = a + b\n"
            "    return total\n"
            "\n"
        )
        result = parse_source(content, "add.py")
        sym = result.symbols[0]
        self.assertEqual(sym.start_line, 1)
        # body lines are 1..3; closes when next line is non-indented blank
        self.assertEqual(sym.end_line, 3)

    def test_python_class_with_method_closes_on_next_top_level(self) -> None:
        content = (
            "class Greeter:\n"
            "    def hello(self):\n"
            "        return 'hi'\n"
            "\n"
            "def bye():\n"
            "    return 'bye'\n"
        )
        result = parse_source(content, "greeter.py")
        names = [s.name for s in result.symbols]
        # Top-level symbols only: nested `hello` is indented relative to
        # the class, so the class still closes when `def bye` appears.
        self.assertIn("Greeter", names)
        self.assertIn("bye", names)

    def test_js_function_end_line_at_closing_brace(self) -> None:
        content = (
            "function add(a, b) {\n"
            "    const x = a;\n"
            "    return x + b;\n"
            "}\n"
        )
        result = parse_source(content, "add.js")
        sym = result.symbols[0]
        self.assertEqual(sym.start_line, 1)
        # closing brace is line 4
        self.assertEqual(sym.end_line, 4)


class ChunkGenerationTests(unittest.TestCase):
    """`parse_source` produces overlapping chunks with correct line ranges."""

    def test_short_file_single_chunk(self) -> None:
        content = "line one\nline two\nline three"
        result = parse_source(content, "short.py")
        self.assertEqual(len(result.chunks), 1)
        chunk = result.chunks[0]
        self.assertIsInstance(chunk, FileChunk)
        self.assertEqual(chunk.chunk_index, 0)
        self.assertEqual(chunk.start_line, 1)
        self.assertEqual(chunk.end_line, 3)
        self.assertEqual(chunk.content, content)

    def test_each_chunk_has_matching_content(self) -> None:
        lines = [f"line {i}" for i in range(120)]
        content = "\n".join(lines) + "\n"
        result = parse_source(content, "big.py")
        self.assertGreater(len(result.chunks), 1)
        for chunk in result.chunks:
            expected = "\n".join(lines[chunk.start_line - 1: chunk.end_line])
            self.assertEqual(chunk.content, expected)

    def test_chunk_line_ranges_are_one_based_and_inclusive(self) -> None:
        lines = [f"line {i}\n" for i in range(80)]
        content = "".join(lines)
        result = parse_source(content, "eighty.py")
        for chunk in result.chunks:
            self.assertGreaterEqual(chunk.start_line, 1)
            self.assertGreaterEqual(chunk.end_line, chunk.start_line)
            self.assertLessEqual(chunk.end_line, len(lines))

    def test_chunk_indices_are_sequential(self) -> None:
        lines = [f"line {i}\n" for i in range(150)]
        content = "".join(lines)
        result = parse_source(content, "long.py")
        indices = [c.chunk_index for c in result.chunks]
        self.assertEqual(indices, list(range(len(result.chunks))))

    def test_chunk_content_sha_matches_sha256(self) -> None:
        content = "def f():\n    return 1\n"
        result = parse_source(content, "f.py")
        for chunk in result.chunks:
            self.assertEqual(
                chunk.content_sha,
                content_sha256(chunk.content),
            )

    def test_empty_content_no_chunks(self) -> None:
        result = parse_source("", "empty.py")
        self.assertEqual(result.chunks, ())
        self.assertEqual(result.symbols, ())


class ContentSha256Tests(unittest.TestCase):
    """`content_sha256` is deterministic and stable across call boundaries."""

    def test_deterministic_for_string(self) -> None:
        a = content_sha256("hello world")
        b = content_sha256("hello world")
        self.assertEqual(a, b)

    def test_different_strings_produce_different_hashes(self) -> None:
        self.assertNotEqual(
            content_sha256("alpha"),
            content_sha256("beta"),
        )

    def test_hash_is_64_hex_chars(self) -> None:
        h = content_sha256("anything")
        self.assertEqual(len(h), 64)
        int(h, 16)  # raises if non-hex

    def test_parse_source_sets_content_sha(self) -> None:
        result = parse_source("x = 1\n", "x.py")
        self.assertEqual(result.content_sha, content_sha256("x = 1\n"))

    def test_parse_source_explicit_sha_is_preserved(self) -> None:
        sentinel = "deadbeef" * 8
        result = parse_source("x = 1\n", "x.py", content_sha=sentinel)
        self.assertEqual(result.content_sha, sentinel)


class IsExcludedPathTests(unittest.TestCase):
    """`is_excluded_path` matches the configured default exclusion patterns."""

    def setUp(self) -> None:
        # The function memoizes compiled patterns into a module-global;
        # reset it between tests so each one sees the config it
        # constructed itself.
        import hermes.indexer.utils as utils_mod
        utils_mod._EXCLUDE_PATTERNS = []

    def test_dotenv_is_excluded(self) -> None:
        cfg = _basic_config()
        self.assertTrue(is_excluded_path(".env", cfg))
        self.assertTrue(is_excluded_path("config/.env", cfg))

    def test_pycache_is_excluded(self) -> None:
        cfg = _basic_config()
        self.assertTrue(is_excluded_path("__pycache__", cfg))
        self.assertTrue(is_excluded_path("src/__pycache__", cfg))

    def test_node_modules_is_excluded(self) -> None:
        cfg = _basic_config()
        self.assertTrue(is_excluded_path("node_modules", cfg))
        self.assertTrue(is_excluded_path("web/node_modules", cfg))

    def test_pyc_files_are_excluded(self) -> None:
        cfg = _basic_config()
        self.assertTrue(is_excluded_path("module.pyc", cfg))
        self.assertTrue(is_excluded_path("pkg/utils.pyc", cfg))

    def test_minified_assets_are_excluded(self) -> None:
        cfg = _basic_config()
        self.assertTrue(is_excluded_path("app.min.js", cfg))
        self.assertTrue(is_excluded_path("styles.min.css", cfg))

    def test_normal_source_files_are_not_excluded(self) -> None:
        cfg = _basic_config()
        self.assertFalse(is_excluded_path("src/main.py", cfg))
        self.assertFalse(is_excluded_path("README.md", cfg))
        self.assertFalse(is_excluded_path("lib/utils.ts", cfg))

    def test_custom_excludes_are_honoured(self) -> None:
        cfg = IndexerConfig(
            allowlist=(),
            excluded_paths=("secrets", "*.key"),
        )
        self.assertTrue(is_excluded_path("secrets", cfg))
        self.assertTrue(is_excluded_path("tls/server.key", cfg))
        self.assertFalse(is_excluded_path("src/main.py", cfg))

    def test_does_not_match_partial_segment(self) -> None:
        # `.env` pattern must not match a file literally named `.envx`
        cfg = _basic_config()
        self.assertFalse(is_excluded_path(".envx", cfg))


class ParsedFileDataclassTests(unittest.TestCase):
    """`parse_source` returns a ParsedFile with the documented shape."""

    def test_returns_parsed_file_dataclass(self) -> None:
        result = parse_source("x = 1\n", "x.py")
        self.assertIsInstance(result, ParsedFile)

    def test_path_and_language_round_trip(self) -> None:
        result = parse_source("x = 1\n", "lib/x.py")
        self.assertEqual(result.path, "lib/x.py")
        self.assertEqual(result.language, "python")

    def test_symbols_are_extracted_symbol_instances(self) -> None:
        result = parse_source("def f():\n    pass\n", "f.py")
        self.assertTrue(all(isinstance(s, ExtractedSymbol) for s in result.symbols))


if __name__ == "__main__":
    unittest.main()
