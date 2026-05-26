"""Regression tests for two display bugs caught during methodology-extraction
Phase 4 (2026-05-02) when smoke-testing the new TS outliner against real repo
files (`VistaShowcase.tsx` + `useVistaShowcase.ts`).

Both bugs were fixed mid-phase. These tests pin the contract so a future
refactor can't silently re-introduce either shape.

References:
- `projects/methodology-extraction/PROJECT.md § Phase 4 Improvements`
- `projects/mcp-ast-tools-hardening/PROJECT.md § Phase 2 — C.2`
- `KB § PATTERNS/compliance/testing.md § Regression tests in practice`
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.noctus.dev import outline_typescript as ot


def write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(body))
    return p


class TestRegressionTSPrefixUsesKindNotClass:
    """Regression: CLI rendering used to hardcode the keyword `class` for
    every top-level container. Caught 2026-05-02 by methodology-extraction
    Phase 4 smoke against `useVistaShowcase.ts`. Fix: cli.py:545-546 derives
    the prefix from `s.kind` for class / interface / type.

    This test pins the underlying contract — the OutlineResult must surface
    distinct `kind` values for each container shape — so the renderer has
    accurate data to choose from. A renderer regression on top of accurate
    data is a separate (cli-only) bug; this test catches the data-shape
    regression that would force every kind to look like a class.
    """

    def test_class_kind_is_class(self, tmp_path):
        p = write(tmp_path, "a.ts", """
            export class Foo {
                bar(): void {}
            }
        """)
        result = ot.outline_typescript(p)
        kinds = {s.kind for s in result.classes}
        assert "class" in kinds, kinds

    def test_interface_kind_is_interface_not_class(self, tmp_path):
        p = write(tmp_path, "a.ts", """
            export interface Bar {
                id: string;
                value: number;
            }
        """)
        result = ot.outline_typescript(p)
        kinds = [s.kind for s in result.classes]
        assert "interface" in kinds, kinds
        # The pre-fix bug shipped these as "class" — pin that they don't.
        assert all(k != "class" for k in kinds), kinds

    def test_type_alias_kind_is_type_not_class(self, tmp_path):
        p = write(tmp_path, "a.ts", """
            export type Status = 'on' | 'off';
        """)
        result = ot.outline_typescript(p)
        kinds = [s.kind for s in result.classes]
        assert "type" in kinds, kinds
        assert all(k != "class" for k in kinds), kinds


class TestRegressionMultilineImportCollapsedToOneLine:
    """Regression: multi-line `import { … } from "…"` blocks used to
    surface as a Symbol whose `.name` contained the literal source slice
    (including newline characters), corrupting any consumer that printed
    the symbol name on a single line. Caught 2026-05-02 by
    methodology-extraction Phase 4 smoke against `VistaShowcase.tsx`.
    Fix: outline_typescript.py:299-302 collapses whitespace + newlines.
    """

    def test_multiline_named_import_has_no_newlines_in_name(self, tmp_path):
        p = write(tmp_path, "a.tsx", """
            import {
                useState,
                useEffect,
                useCallback,
            } from 'react';
        """)
        result = ot.outline_typescript(p)
        assert result.imports, "expected at least one import"
        for imp in result.imports:
            assert "\n" not in imp.name, (
                f"multi-line import name leaked newlines: {imp.name!r}"
            )

    def test_multiline_import_keeps_essential_tokens(self, tmp_path):
        """The collapse preserves the readable content — just on one line."""
        p = write(tmp_path, "a.tsx", """
            import {
                AlertTriangle,
                Lock,
                ShieldAlert,
            } from 'lucide-react';
        """)
        result = ot.outline_typescript(p)
        assert result.imports
        name = result.imports[0].name
        # All three named imports + the from-clause must survive collapse
        assert "AlertTriangle" in name
        assert "Lock" in name
        assert "ShieldAlert" in name
        assert "lucide-react" in name
        assert "\n" not in name

    def test_real_repo_vistashowcase_imports_have_no_newlines(self, tmp_path):
        """Smoke against the actual file that originally caught the bug.
        Skips if the file isn't present (e.g. running tests outside the
        full repo)."""
        repo_root = Path(__file__).resolve().parents[4]
        target = repo_root / "products/erp-imobiliario/frontend/src/pages/VistaShowcase.tsx"
        if not target.exists():
            pytest.skip(f"target file not present: {target}")
        result = ot.outline_typescript(target)
        for imp in result.imports:
            assert "\n" not in imp.name, (
                f"VistaShowcase.tsx import leaked newlines: {imp.name!r}"
            )
