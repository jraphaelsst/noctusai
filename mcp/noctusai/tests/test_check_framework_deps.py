"""Tests for the noctus.dev.check_framework_deps tool.

Behaviour parity with scripts/check-framework-deps.py: the audit detects a
product missing any FRAMEWORK_DEP; --fix borrows pinned versions from the
erp-imobiliario donor; clean tree → exit 0.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.check_framework_deps import (
    FRAMEWORK_DEPS,
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
