"""Tests for the Python outline tool."""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import outline_python as op


def write(tmp_path: Path, name: str, body: str) -> Path:
    """Helper: write a Python source file under tmp_path."""
    f = tmp_path / name
    f.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return f


class TestMissingFile:
    def test_returns_parse_error(self, tmp_path):
        result = op.outline_python(str(tmp_path / "nope.py"))
        assert result.parse_error is not None
        assert "not found" in result.parse_error
        assert result.symbol_count == 0


class TestSyntaxError:
    def test_reports_line_and_message(self, tmp_path):
        f = write(tmp_path, "broken.py", """
            def foo(:
                return 1
        """)
        result = op.outline_python(str(f))
        assert result.parse_error is not None
        assert "SyntaxError" in result.parse_error
        # Even with a parse error, total_lines is reported.
        assert result.total_lines > 0


class TestModuleLevel:
    def test_function_captured(self, tmp_path):
        f = write(tmp_path, "m.py", """
            def hello():
                return "hi"
        """)
        result = op.outline_python(str(f))
        assert len(result.functions) == 1
        s = result.functions[0]
        assert s.name == "hello"
        assert s.kind == "function"
        assert s.line == 1

    def test_async_function_captured(self, tmp_path):
        f = write(tmp_path, "m.py", """
            async def fetch():
                return None
        """)
        result = op.outline_python(str(f))
        assert len(result.functions) == 1
        assert result.functions[0].kind == "async_function"

    def test_decorators_captured(self, tmp_path):
        f = write(tmp_path, "m.py", """
            from functools import lru_cache

            @lru_cache
            def memoized():
                return 1
        """)
        result = op.outline_python(str(f))
        assert len(result.functions) == 1
        assert "lru_cache" in result.functions[0].decorators[0]

    def test_docstring_first_line(self, tmp_path):
        f = write(tmp_path, "m.py", '''
            def documented():
                """Return the answer.

                Multi-line follow-up that should not appear.
                """
                return 42
        ''')
        result = op.outline_python(str(f))
        assert result.functions[0].docstring_first_line == "Return the answer."


class TestClassesAndMethods:
    def test_class_and_methods_captured(self, tmp_path):
        f = write(tmp_path, "m.py", """
            class Greeter:
                '''Greets things.'''
                def __init__(self, name):
                    self.name = name

                def greet(self):
                    return f"hi {self.name}"

                async def greet_async(self):
                    return f"hi {self.name}"
        """)
        result = op.outline_python(str(f))
        assert len(result.classes) == 1
        cls = result.classes[0]
        assert cls.name == "Greeter"
        assert cls.docstring_first_line == "Greets things."

        assert len(result.methods) == 3
        names = [m.name for m in result.methods]
        assert names == ["__init__", "greet", "greet_async"]
        assert all(m.parent == "Greeter" for m in result.methods)
        assert result.methods[2].kind == "async_method"


class TestConstants:
    def test_upper_snake_case_assignment_captured(self, tmp_path):
        f = write(tmp_path, "m.py", """
            DEFAULT_TIMEOUT = 15
            MAX_RETRIES = 3
            non_constant = "skip"
        """)
        result = op.outline_python(str(f))
        names = [c.name for c in result.constants]
        assert "DEFAULT_TIMEOUT" in names
        assert "MAX_RETRIES" in names
        assert "non_constant" not in names

    def test_annotated_constant_captured(self, tmp_path):
        f = write(tmp_path, "m.py", """
            DEFAULT_LIMIT: int = 50
            other_var: str = "hello"
        """)
        result = op.outline_python(str(f))
        names = [c.name for c in result.constants]
        assert "DEFAULT_LIMIT" in names
        assert "other_var" not in names


class TestImports:
    def test_import_and_from_captured(self, tmp_path):
        f = write(tmp_path, "m.py", """
            import os
            import sys
            from pathlib import Path
        """)
        result = op.outline_python(str(f))
        assert len(result.imports) == 3
        assert result.imports[0].name == "import os"
        assert result.imports[2].name == "from pathlib import Path"

    def test_multiline_from_import(self, tmp_path):
        f = write(tmp_path, "m.py", """
            from typing import (
                Any,
                Optional,
            )
        """)
        result = op.outline_python(str(f))
        assert len(result.imports) == 1
        # The imports name carries the original multiline source slice
        assert "Optional" in result.imports[0].name


class TestSymbolCount:
    def test_aggregate_count(self, tmp_path):
        f = write(tmp_path, "m.py", """
            import os

            DEFAULT = 1

            def f():
                pass

            class C:
                def m(self):
                    pass
        """)
        result = op.outline_python(str(f))
        # symbol_count = classes + functions + methods + constants
        # imports are not in symbol_count (they're navigation, not a "symbol")
        assert result.symbol_count == 1 + 1 + 1 + 1
        assert len(result.imports) == 1


class TestSerialization:
    def test_to_dict_round_trip(self, tmp_path):
        f = write(tmp_path, "m.py", """
            def f():
                pass
        """)
        result = op.outline_python(str(f))
        d = result.to_dict()
        assert d["path"]
        assert d["total_lines"] >= 1
        assert d["parse_error"] is None
        assert d["functions"][0]["name"] == "f"
        assert "kind" in d["functions"][0]
        # symbol_count derived field present
        assert d["symbol_count"] == 1
        # schema_version field locks the contract for MCP host consumers.
        # Bumping past 1 is a backward-incompatible change — see the
        # OutlineResult docstring's Versioning paragraph.
        assert result.schema_version == 1
        assert d["schema_version"] == 1


class TestRealWorldFile:
    def test_outlines_an_actual_repo_file(self):
        """Smoke test: outline a real file from the repo. Sanity-check on a
        non-toy example."""
        repo_root = Path(__file__).resolve().parents[3]
        target = repo_root / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "cost_evaluation.py"
        result = op.outline_python(str(target))
        assert result.parse_error is None
        # Should have FileTokenCount and TokenCountResult dataclasses + count_tokens function
        class_names = {c.name for c in result.classes}
        assert "FileTokenCount" in class_names
        assert "TokenCountResult" in class_names
        function_names = {f.name for f in result.functions}
        assert "count_tokens" in function_names
