"""Regression tests for `check_module_page_status_rows` (warn-first; roadmap crm-cms-erp-vertical-seeds ADR-1)."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_module_page_status_rows,
    lower_module_page_status_rows_baseline,
)

_BASELINE = ("mcp", "noctusai", "tests", "module_page_status_rows_baseline.json")
_SPEC = 'from noctusai_seed.modules import ModuleSpec, PageSpec\nM = ModuleSpec(key="crm", pages=(PageSpec(key="crm_leads", path="/crm/leads", label="Leads"),))\n'
_FACTORY = 'def crm_module():\n    return ModuleSpec(key="crm", pages=(PageSpec(key="crm_leads", path="/crm/leads", label="Leads"),))\n'
_SEED_SQL = "INSERT INTO demo.status_pagina (nome_pagina, status) VALUES ('crm_leads', 'producao');\n"
_FE = "defineModule({ key: 'crm', items: [{ label: 'L', path: '/crm/leads', pageKey: 'crm_leads' }] });\n"
_MAIN = "products/demo/backend/app/main.py"


def _tree(tmp_path: Path, files: dict[str, str], baseline: dict | None = None) -> Path:
    (tmp_path / "deploy" / "fleet").mkdir(parents=True)
    (tmp_path / "deploy" / "fleet" / "active-scope.txt").write_text("demo\ncore\n", encoding="utf-8")
    for rel, text in files.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    b = tmp_path.joinpath(*_BASELINE)
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text(json.dumps({"produtos": baseline or {}}), encoding="utf-8")
    return tmp_path


class TestModulePageStatusRows:
    def test_declared_page_without_status_pagina_row_is_flagged_as_warning(self, tmp_path):
        root = _tree(tmp_path, {_MAIN: _SPEC})
        issues = check_module_page_status_rows(repo_root=root)
        assert len(issues) == 1 and issues[0]["severity"] == "warning" and "crm_leads" in issues[0]["issue"]

    def test_seeded_row_is_green(self, tmp_path):
        root = _tree(tmp_path, {_MAIN: _SPEC, "products/demo/backend/migrations/001_x.sql": _SEED_SQL})
        assert check_module_page_status_rows(repo_root=root) == []

    def test_no_modules_is_green(self, tmp_path):
        assert check_module_page_status_rows(repo_root=_tree(tmp_path, {_MAIN: "X = 1\n"})) == []

    def test_seed_factory_called_by_a_product_declares_its_pages(self, tmp_path):
        root = _tree(tmp_path, {
            "seed/framework/backend/noctusai_seed/modules/crm.py": _FACTORY,
            _MAIN: "from x import crm_module\nMODS = [crm_module()]\n",
        })
        assert "crm_leads" in check_module_page_status_rows(repo_root=root)[0]["issue"]

    def test_escape_marker_with_reason(self, tmp_path):
        src = _SPEC.replace("M = ", "# noc-allow: module-page-status-row — seeded by a later migration, W2-4\nM = ")
        assert check_module_page_status_rows(repo_root=_tree(tmp_path, {_MAIN: src})) == []

    def test_baseline_absorbs_gap_and_flags_stale_entry(self, tmp_path):
        root = _tree(tmp_path, {_MAIN: _SPEC}, baseline={"demo": ["crm_leads"]})
        assert check_module_page_status_rows(repo_root=root) == []
        (root / "products/demo/backend/migrations").mkdir(parents=True)
        (root / "products/demo/backend/migrations/001_x.sql").write_text(_SEED_SQL, encoding="utf-8")
        assert "drop it" in check_module_page_status_rows(repo_root=root)[0]["issue"]
        assert lower_module_page_status_rows_baseline(root) == {}

    @pytest.mark.skipif(shutil.which("node") is None, reason="needs node + ts-morph")
    def test_fe_define_module_page_key_is_checked(self, tmp_path):
        root = _tree(tmp_path, {"products/demo/frontend/src/modules.ts": _FE})
        assert "crm_leads" in check_module_page_status_rows(repo_root=root)[0]["issue"]
