"""`check_local_pipeline_board` — red/green fixtures on synthetic trees (awake scope via a real active-scope.txt)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import compliance as c  # noqa: E402

MARK_PY = "# NOC-REMEDIATE[pipeline-board-organ]: local copy — 2026-11-07\n"
MARK_TSX = "// NOC-REMEDIATE[pipeline-board-organ]: local copy — 2026-11-07\n"
BE = "products/awake/backend/app/routers/boards.py"
FE = "products/awake/frontend/src/pages/Funil.tsx"


def _tree(tmp_path, files: dict[str, str], baseline: int | None = None, awake=("awake",)):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    scope = tmp_path / "deploy/fleet/active-scope.txt"
    scope.parent.mkdir(parents=True, exist_ok=True)
    scope.write_text("\n".join(awake) + "\n")
    if baseline is not None:
        b = tmp_path.joinpath(*c._LPB_BASELINE_REL)
        b.parent.mkdir(parents=True, exist_ok=True)
        b.write_text(json.dumps({"count": baseline}))
    return tmp_path


class TestCheckLocalPipelineBoard:
    def test_flags_mover_etapa_route(self, tmp_path):
        root = _tree(tmp_path, {BE: '@r.post("/{id}/mover-etapa")\ndef mv(id): ...\n'}, baseline=0)
        out = c.check_local_pipeline_board(repo_root=root)
        assert [i["file"] for i in out] == [BE] and out[0]["severity"] == "warning"

    def test_flags_move_card_and_group_calls(self, tmp_path):
        src = "from x import move_card\nmove_card(1)\nlib.group_into_colunas(2)\n"
        out = c.check_local_pipeline_board(repo_root=_tree(tmp_path, {BE: src}, baseline=0))
        assert len(out) == 1 and "move_card" in out[0]["issue"] and "group_into_colunas" in out[0]["issue"]

    def test_flags_board_renders(self, tmp_path):
        files = {FE: "export const A = () => <PipelineBoard a={1} />;\n",
                 "products/awake/frontend/src/K.tsx": "const B = <KanbanBoard<X> />;\n"}
        assert len(c.check_local_pipeline_board(repo_root=_tree(tmp_path, files, baseline=0))) == 2

    def test_funnel_board_and_tests_are_clean(self, tmp_path):
        files = {
            "products/awake/frontend/src/FunnelBoard.tsx": "const A = <PipelineBoard />;\n",
            "products/awake/frontend/src/Funil.test.tsx": "const A = <PipelineBoard />;\n",
            "products/awake/backend/tests/test_b.py": "move_card(1)\n",
            "products/awake/backend/app/ok.py": "def f():\n    return 1\n",
        }
        assert c.check_local_pipeline_board(repo_root=_tree(tmp_path, files, baseline=0)) == []

    def test_marker_exempts_file(self, tmp_path):
        files = {BE: MARK_PY + "move_card(1)\n", FE: MARK_TSX + "const A = <PipelineBoard />;\n"}
        assert c.check_local_pipeline_board(repo_root=_tree(tmp_path, files, baseline=2)) == []

    def test_marker_in_string_does_not_exempt(self, tmp_path):
        src = 'X = "NOC-REMEDIATE[pipeline-board-organ]: x"\nmove_card(1)\n'
        assert len(c.check_local_pipeline_board(repo_root=_tree(tmp_path, {BE: src}, baseline=0))) == 1

    def test_asleep_product_not_checked(self, tmp_path):
        root = _tree(tmp_path, {BE.replace("awake", "asleep"): "move_card(1)\n", "products/awake/x.txt": ""}, baseline=0)
        assert c.check_local_pipeline_board(repo_root=root) == []

    def test_ratchet_grows_flagged_even_for_asleep_marker(self, tmp_path):
        root = _tree(tmp_path, {BE.replace("awake", "asleep"): MARK_PY + "move_card(1)\n"}, baseline=0)
        out = c.check_local_pipeline_board(repo_root=root)
        assert len(out) == 1 and "baseline 0" in out[0]["issue"]

    def test_ratchet_at_baseline_clean_and_missing_baseline_flagged(self, tmp_path):
        files = {BE: MARK_PY + "move_card(1)\n"}
        assert c.check_local_pipeline_board(repo_root=_tree(tmp_path, files, baseline=1)) == []
        out = c.check_local_pipeline_board(repo_root=_tree(tmp_path / "b", files))
        assert len(out) == 1 and "baseline missing" in out[0]["issue"]

    def test_refresh_only_shrinks(self, tmp_path):
        root = _tree(tmp_path, {BE: MARK_PY + "x = 1\n"}, baseline=5)
        assert c.refresh_pipeline_board_markers_baseline(root) == 1
        (root / BE).write_text(MARK_PY + "x = 1\n")
        (root / "products/awake/backend/b.py").write_text(MARK_PY)
        (root / "products/awake/backend/c.py").write_text(MARK_PY)
        assert c.refresh_pipeline_board_markers_baseline(root) == 1  # never grows

    def test_paths_scope_narrows_reporting(self, tmp_path):
        root = _tree(tmp_path, {BE: "move_card(1)\n"}, baseline=0)
        assert c.check_local_pipeline_board(paths=["other.py"], repo_root=root) == []
        assert len(c.check_local_pipeline_board(paths=[BE], repo_root=root)) == 1
