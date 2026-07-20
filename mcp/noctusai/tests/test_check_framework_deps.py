"""Tests for the noctus.dev.check_framework_deps tool.

Behaviour parity with scripts/check-framework-deps.py: the audit detects a
product missing any FRAMEWORK_DEP; --fix borrows pinned versions from the
erp-imobiliario donor; clean tree → exit 0.

The ``TestOrganTransitiveDeps`` class is the regression coverage for the
2026-07-20 blind-spot fix: a NEW peer dep appearing in a
``seed/lib/frontend/src`` organ (the ``KanbanBoard``/``@dnd-kit/*``
incident) must be caught by the checker WITHOUT anyone editing
``FRAMEWORK_DEPS`` by hand — that's the actual deliverable, not the one-time
backfill.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.check_framework_deps import (
    FRAMEWORK_DEPS,
    ORGAN_SOURCE_DIR,
    _derive_organ_transitive_deps,
    _package_name_from_specifier,
    _strip_comments,
    check_framework_deps,
)


def _write_pkg(root: Path, slug: str, deps: dict, dev_deps: dict | None = None) -> None:
    pdir = root / "products" / slug / "frontend"
    pdir.mkdir(parents=True)
    payload = {"name": slug, "dependencies": deps}
    if dev_deps is not None:
        payload["devDependencies"] = dev_deps
    (pdir / "package.json").write_text(json.dumps(payload, indent=2))


def _full_deps() -> dict:
    return {d: "1.0.0" for d in FRAMEWORK_DEPS}


class TestAuditClean:
    def test_all_products_complete_is_clean(self, tmp_path):
        _write_pkg(tmp_path, "erp-imobiliario", _full_deps())
        _write_pkg(tmp_path, "therapy-platform", _full_deps())
        result = check_framework_deps(repo_root=tmp_path)
        assert result["status"] == "clean"
        assert result["exit_code"] == 0
        assert result["drift"] == {}
        assert result["total_missing"] == 0
        assert result["products_audited"] == 2

    def test_deps_split_across_dependencies_and_devDependencies(self, tmp_path):
        half = FRAMEWORK_DEPS[:6]
        rest = FRAMEWORK_DEPS[6:]
        _write_pkg(
            tmp_path, "erp-imobiliario",
            {d: "1.0.0" for d in half},
            {d: "1.0.0" for d in rest},
        )
        result = check_framework_deps(repo_root=tmp_path)
        assert result["status"] == "clean"


class TestAuditDrift:
    def test_missing_dep_detected_exit_1(self, tmp_path):
        partial = {d: "1.0.0" for d in FRAMEWORK_DEPS if d != "zustand"}
        _write_pkg(tmp_path, "erp-imobiliario", _full_deps())
        _write_pkg(tmp_path, "social-wiring", partial)
        result = check_framework_deps(repo_root=tmp_path)
        assert result["status"] == "drift"
        assert result["exit_code"] == 1
        assert result["drift"] == {"social-wiring": ["zustand"]}
        assert result["total_missing"] == 1
        assert result["fixed"] == 0

    def test_multiple_products_multiple_missing(self, tmp_path):
        _write_pkg(tmp_path, "erp-imobiliario", _full_deps())
        _write_pkg(
            tmp_path, "a-prod",
            {d: "1.0.0" for d in FRAMEWORK_DEPS if d not in ("clsx", "sonner")},
        )
        _write_pkg(
            tmp_path, "b-prod",
            {d: "1.0.0" for d in FRAMEWORK_DEPS if d != "react-dom"},
        )
        result = check_framework_deps(repo_root=tmp_path)
        assert result["total_missing"] == 3
        assert set(result["drift"]) == {"a-prod", "b-prod"}


class TestFix:
    def test_fix_borrows_donor_versions_and_writes(self, tmp_path):
        donor_deps = {d: f"^{i}.0.0" for i, d in enumerate(FRAMEWORK_DEPS)}
        _write_pkg(tmp_path, "erp-imobiliario", donor_deps)
        partial = {d: "1.0.0" for d in FRAMEWORK_DEPS if d != "lucide-react"}
        _write_pkg(tmp_path, "social-wiring", partial)

        result = check_framework_deps(repo_root=tmp_path, fix=True)
        assert result["status"] == "fixed"
        assert result["exit_code"] == 0
        assert result["fixed"] == 1

        # The package.json on disk now lists lucide-react at the donor version.
        pkg = json.loads(
            (tmp_path / "products" / "social-wiring" / "frontend" / "package.json").read_text()
        )
        idx = FRAMEWORK_DEPS.index("lucide-react")
        assert pkg["dependencies"]["lucide-react"] == f"^{idx}.0.0"
        # And it sorts deps.
        assert list(pkg["dependencies"]) == sorted(pkg["dependencies"])

        # Re-audit → now clean.
        re_audit = check_framework_deps(repo_root=tmp_path)
        assert re_audit["status"] == "clean"

    def test_fix_falls_back_to_star_when_donor_lacks_dep(self, tmp_path):
        # Donor itself missing 'sonner' → fix uses "*".
        donor_deps = {d: "1.0.0" for d in FRAMEWORK_DEPS if d != "sonner"}
        _write_pkg(tmp_path, "erp-imobiliario", donor_deps)
        partial = {d: "1.0.0" for d in FRAMEWORK_DEPS if d != "sonner"}
        _write_pkg(tmp_path, "x-prod", partial)
        result = check_framework_deps(repo_root=tmp_path, fix=True)
        assert result["status"] == "fixed"
        pkg = json.loads(
            (tmp_path / "products" / "x-prod" / "frontend" / "package.json").read_text()
        )
        assert pkg["dependencies"]["sonner"] == "*"


def _write_organ_source(root: Path, rel_path: str, content: str) -> None:
    path = root / ORGAN_SOURCE_DIR / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class TestOrganTransitiveDerivation:
    """Unit coverage for `_derive_organ_transitive_deps` in isolation."""

    def test_no_organ_source_dir_is_a_noop(self, tmp_path):
        assert _derive_organ_transitive_deps(tmp_path) == []

    def test_derives_a_new_external_package(self, tmp_path):
        _write_organ_source(
            tmp_path, "components/NewOrgan.tsx",
            'import { useDragDrop } from "@acme/new-peer-dep";\n'
            "export function NewOrgan() { return useDragDrop(); }\n",
        )
        assert "@acme/new-peer-dep" in _derive_organ_transitive_deps(tmp_path)

    def test_excludes_relative_alias_and_self_imports(self, tmp_path):
        _write_organ_source(
            tmp_path, "components/Local.tsx",
            'import { cn } from "../utils";\n'
            'import { Foo } from "@/hooks/useFoo";\n'
            'import { createProductApp } from "@noctusai/seed";\n'
            'import { real } from "a-real-external-pkg";\n',
        )
        found = _derive_organ_transitive_deps(tmp_path)
        assert found == ["a-real-external-pkg"]

    def test_excludes_type_only_import_and_export(self, tmp_path):
        _write_organ_source(
            tmp_path, "types.ts",
            'import type { Config } from "type-only-pkg";\n'
            'export type { Other } from "also-type-only";\n',
        )
        assert _derive_organ_transitive_deps(tmp_path) == []

    def test_excludes_test_files(self, tmp_path):
        _write_organ_source(
            tmp_path, "components/Thing.test.tsx",
            'import { render } from "@testing-library/react";\n',
        )
        assert _derive_organ_transitive_deps(tmp_path) == []

    def test_multiline_import_and_subpath_normalization(self, tmp_path):
        _write_organ_source(
            tmp_path, "stores.ts",
            "import {\n"
            "  devtools,\n"
            "  persist,\n"
            '} from "zustand/middleware";\n',
        )
        assert _derive_organ_transitive_deps(tmp_path) == ["zustand"]

    def test_scoped_subpath_normalizes_to_scope_plus_name(self):
        assert _package_name_from_specifier("@dnd-kit/sortable") == "@dnd-kit/sortable"
        assert _package_name_from_specifier("@dnd-kit/sortable/utilities") == "@dnd-kit/sortable"
        assert _package_name_from_specifier("lucide-react/icons/x") == "lucide-react"
        assert _package_name_from_specifier("./relative") is None
        assert _package_name_from_specifier("@/local-alias") is None
        assert _package_name_from_specifier("@noctusai/lib") is None

    def test_strip_comments_prevents_prose_import_false_anchor(self, tmp_path):
        """Regression for the exact false-positive this scanner hit against
        seed/lib/frontend/src/design-system/tailwind.config.base.ts: a
        JSDoc block whose PROSE contains the word "import" (no semicolon
        inside the comment to stop the lazy `[^;]*?` quantifier) let the
        regex anchor on the comment text and lazily extend straight
        through to the NEXT real `from "spec"` after the comment closes —
        stealing that import's specifier and losing its `type` prefix.
        """
        text = (
            "/**\n"
            " * NOTE: This file must NOT import external packages\n"
            " * because doing so breaks the loader.\n"
            " */\n"
            'import type { Config } from "should-not-appear";\n'
        )
        assert _strip_comments(text).count("import") == 1  # only the real one survives
        _write_organ_source(tmp_path, "commented.ts", text)
        assert _derive_organ_transitive_deps(tmp_path) == []

    def test_line_comment_with_import_word_is_not_a_false_anchor(self, tmp_path):
        _write_organ_source(
            tmp_path, "linecomment.ts",
            "// don't import from over there\n"
            'import { real } from "genuinely-real-pkg";\n',
        )
        assert _derive_organ_transitive_deps(tmp_path) == ["genuinely-real-pkg"]


class TestOrganTransitiveEndToEnd:
    """The actual deliverable: a NEW peer dep in a seed/lib organ is caught
    by the full audit + surfaced in the result, WITHOUT any FRAMEWORK_DEPS
    edit — and --fix backfills it same as any other missing dep."""

    def test_new_organ_dep_flagged_as_drift_without_framework_deps_edit(self, tmp_path):
        _write_organ_source(
            tmp_path, "components/kanban/NewFeature.tsx",
            'import { useSensor } from "@dnd-kit/core";\n'
            'import { useMagicPeerDep } from "@acme/magic-peer-dep";\n',
        )
        _write_pkg(tmp_path, "erp-imobiliario", _full_deps())
        # A product with every hand-curated FRAMEWORK_DEP but NOT the new
        # organ-only peer dep — exactly the KanbanBoard/@dnd-kit incident
        # shape (checker used to report "clean" here).
        _write_pkg(tmp_path, "some-product", _full_deps())

        result = check_framework_deps(repo_root=tmp_path)

        assert result["status"] == "drift"
        assert "@acme/magic-peer-dep" in result["organ_transitive_deps"]
        assert "@acme/magic-peer-dep" in result["drift"]["some-product"]
        # And FRAMEWORK_DEPS itself was never touched.
        assert "@acme/magic-peer-dep" not in FRAMEWORK_DEPS

    def test_fix_backfills_the_derived_dep_from_donor(self, tmp_path):
        _write_organ_source(
            tmp_path, "components/kanban/NewFeature.tsx",
            'import { useMagicPeerDep } from "@acme/magic-peer-dep";\n',
        )
        donor_deps = _full_deps()
        donor_deps["@acme/magic-peer-dep"] = "^9.9.9"
        _write_pkg(tmp_path, "erp-imobiliario", donor_deps)
        _write_pkg(tmp_path, "some-product", _full_deps())

        result = check_framework_deps(repo_root=tmp_path, fix=True)
        assert result["status"] == "fixed"

        pkg = json.loads(
            (tmp_path / "products" / "some-product" / "frontend" / "package.json").read_text()
        )
        assert pkg["dependencies"]["@acme/magic-peer-dep"] == "^9.9.9"

        re_audit = check_framework_deps(repo_root=tmp_path)
        assert re_audit["status"] == "clean"

    def test_clean_tree_reports_the_derived_list_even_when_empty(self, tmp_path):
        # No ORGAN_SOURCE_DIR at all (synthetic root) → organ_transitive_deps
        # is present and empty, never absent — callers can rely on the key.
        _write_pkg(tmp_path, "erp-imobiliario", _full_deps())
        result = check_framework_deps(repo_root=tmp_path)
        assert result["status"] == "clean"
        assert result["organ_transitive_deps"] == []
        assert "manual_only_scope" in result


class TestMcpRegistration:
    def test_register_callable(self):
        from tools.noctus.dev.check_framework_deps import register
        assert callable(register)

    def test_register_wires_tool_onto_a_server(self):
        """The module's own register() wires the tool. (Global build_server()
        wiring lands when the architect adds check_framework_deps to
        tools/noctus/dev/__init__.py per the integration recipe.)"""
        from mcp.server.fastmcp import FastMCP

        from tools.noctus.dev.check_framework_deps import register
        s = FastMCP(name="t")
        register(s)
        assert "noctus.dev.check_framework_deps" in s._tool_manager._tools
