"""Regression tests for `check_stage_list_not_in_code` (warn-first; roadmap crm-cms-erp-vertical-seeds ADR-2)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_stage_list_not_in_code,
    lower_stage_list_not_in_code_baseline,
    stage_list_hits,
)

_BASELINE = ("mcp", "noctusai", "tests", "stage_list_not_in_code_baseline.json")
_ROUTER = "products/demo/backend/app/routers/leads.py"


def _tree(tmp_path: Path, files: dict[str, str], baseline: dict[str, int] | None = None) -> Path:
    (tmp_path / "deploy" / "fleet").mkdir(parents=True)
    (tmp_path / "deploy" / "fleet" / "active-scope.txt").write_text("demo\ncore\n", encoding="utf-8")
    for rel, text in files.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    b = tmp_path.joinpath(*_BASELINE)
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text(json.dumps({"arquivos": baseline or {}}), encoding="utf-8")
    return tmp_path


class TestStageListNotInCode:
    def test_literal_stage_tuple_in_router_is_flagged_as_warning(self, tmp_path):
        root = _tree(tmp_path, {_ROUTER: 'STAGES = ("novo", "contatado", "proposta", "ganho")\n'})
        issues = check_stage_list_not_in_code(repo_root=root)
        assert len(issues) == 1 and issues[0]["severity"] == "warning" and issues[0]["file"] == _ROUTER

    def test_stage_default_call_and_import_alias_are_flagged(self, tmp_path):
        src = "from noctusai_lib.domain.pipeline.defaults import StageDefault as S\nX = [S('novo', 'Novo'), S('ganho', 'Ganho')]\n"
        assert [k for _, k in stage_list_hits(src)] == ["S(...) literal", "S(...) literal"]

    def test_clean_tree_is_green(self, tmp_path):
        root = _tree(tmp_path, {_ROUTER: 'ROLES = ("admin", "member")\nPAGE = ("a", "b", "c")\n'})
        assert check_stage_list_not_in_code(repo_root=root) == []

    def test_variable_slug_is_the_mechanism_not_a_literal(self):
        assert stage_list_hits("def f(x):\n    return LeadStage(slug=x, label=x)\n") == []

    def test_market_crm_preset_is_the_allowed_home(self, tmp_path):
        root = _tree(tmp_path, {"products/demo/backend/app/market/crm_preset.py": 'S = ("novo", "contatado", "proposta")\n'})
        assert check_stage_list_not_in_code(repo_root=root) == []

    def test_escape_marker_with_reason_silences_but_bare_marker_does_not(self):
        ok = '# noc-allow: stage-list — roles vocabulary, not a funnel\nR = ("novo", "contatado", "proposta")\n'
        bare = '# noc-allow: stage-list\nR = ("novo", "contatado", "proposta")\n'
        assert stage_list_hits(ok) == []
        assert len(stage_list_hits(bare)) == 1

    def test_baseline_absorbs_existing_and_flags_new_and_stale(self, tmp_path):
        root = _tree(tmp_path, {_ROUTER: 'A = ("novo", "contatado", "proposta")\n'}, baseline={_ROUTER: 1})
        assert check_stage_list_not_in_code(repo_root=root) == []
        (root / _ROUTER).write_text('A = ("novo", "contatado", "proposta")\nB = ("novo", "ganho", "perdido")\n', encoding="utf-8")
        assert "baseline allows 1" in check_stage_list_not_in_code(repo_root=root)[0]["issue"]
        (root / _ROUTER).write_text("A = 1\n", encoding="utf-8")
        assert "lower" in check_stage_list_not_in_code(repo_root=root)[0]["issue"]
        assert lower_stage_list_not_in_code_baseline(root) == {}
