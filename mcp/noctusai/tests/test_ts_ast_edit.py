"""Tests for `noctus.dev.ts_ast_rename_symbol` — a real ts-morph AST edit.

Node/ts-morph must be reachable (`mcp/noctusai/node/` + `npm install`) for
the happy-path assertions to run. Per the AST-first rule
(`KB § PATTERNS/common/ast.md`), the point of this tool is that it does
what regex cannot: rename only the real references to a symbol, leaving a
same-spelled string literal / comment untouched. If `node` isn't on PATH
in the test environment, the suite skips loudly with a named reason
(never silently "passes" without exercising the AST edit) — the
`node_unavailable` typed-error path is asserted separately and does NOT
require node at all.
"""
from __future__ import annotations

import shutil
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import ts_ast_edit as tae

_NODE_AVAILABLE = shutil.which("node") is not None
_HELPER_INSTALLED = tae._TS_AST_EDIT_SCRIPT.exists() and (tae._NODE_HELPER_DIR / "node_modules").exists()

_SKIP_REASON = (
    "node not on PATH in this test environment"
    if not _NODE_AVAILABLE
    else "mcp/noctusai/node/ helper not installed (run `npm install` in mcp/noctusai/node/)"
)

requires_ts_morph = pytest.mark.skipif(
    not (_NODE_AVAILABLE and _HELPER_INSTALLED), reason=_SKIP_REASON
)


def write_fixture(tmp_path: Path, name: str, body: str) -> Path:
    f = tmp_path / name
    f.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return f


class TestNodeUnavailableDegradesHonestly:
    """This path needs NO node install — it asserts the typed-error shape
    when `node` genuinely can't be found, so it always runs."""

    def test_missing_node_binary_returns_typed_error(self, tmp_path, monkeypatch):
        f = write_fixture(tmp_path, "m.ts", """
            export const oldName = 1;
        """)
        monkeypatch.setattr(tae.shutil, "which", lambda _: None)
        result = tae.ts_ast_rename_symbol(str(f), "oldName", "newName")
        assert result.ok is False
        assert result.status == "node_unavailable"
        assert result.error is not None
        # No silent no-op AND no file mutation attempted.
        assert f.read_text(encoding="utf-8") == "export const oldName = 1;\n"


@requires_ts_morph
class TestRenameSymbolRealAstEdit:
    def test_renames_declaration_and_call_sites_only(self, tmp_path):
        """The case regex gets wrong: a same-spelled string literal and a
        comment must survive untouched; only the real declaration + the two
        real call-site references change."""
        f = write_fixture(tmp_path, "fixture.ts", """
            export const oldName = (x: number): number => {
              return x + 1;
            };

            export function useIt(): number {
              const s = "oldName"; // should NOT be renamed (string literal)
              console.log(s);
              return oldName(1) + oldName(2);
            }
        """)

        result = tae.ts_ast_rename_symbol(str(f), "oldName", "newName")

        assert result.ok is True, result.error
        assert result.status == "renamed"
        assert result.old_name == "oldName"
        assert result.new_name == "newName"
        # 2 real call-site references (declaration renamed unconditionally,
        # not counted in referencesUpdated per the node script's contract).
        assert result.references_updated == 2
        assert result.declaration_kind == "VariableDeclaration"

        after = f.read_text(encoding="utf-8")
        assert "export const newName = " in after
        assert "newName(1) + newName(2)" in after
        # The string literal and comment are untouched — the exact thing a
        # `sed -i 's/oldName/newName/g'` would have gotten wrong.
        assert '"oldName"' in after
        assert "// should NOT be renamed" in after

    def test_symbol_not_found_returns_typed_error(self, tmp_path):
        f = write_fixture(tmp_path, "m.ts", """
            export const somethingElse = 1;
        """)
        result = tae.ts_ast_rename_symbol(str(f), "doesNotExist", "newName")
        assert result.ok is False
        assert result.status == "symbol_not_found"
        assert result.error is not None
        # File must be untouched on a not-found error.
        assert "somethingElse" in f.read_text(encoding="utf-8")
        assert "doesNotExist" not in f.read_text(encoding="utf-8")

    def test_function_declaration_rename(self, tmp_path):
        f = write_fixture(tmp_path, "m2.ts", """
            export function greet(name: string): string {
              return `hi ${name}`;
            }

            export function callGreet(): string {
              return greet("world");
            }
        """)
        result = tae.ts_ast_rename_symbol(str(f), "greet", "sayHello")
        assert result.ok is True, result.error
        assert result.declaration_kind == "FunctionDeclaration"
        after = f.read_text(encoding="utf-8")
        assert "function sayHello(" in after
        assert "sayHello(\"world\")" in after
        assert "greet" not in after
