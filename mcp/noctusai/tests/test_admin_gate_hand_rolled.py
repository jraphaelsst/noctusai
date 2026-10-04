"""Regression tests for `check_admin_gate_hand_rolled` (platform-admin-mfa §5 point 8)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_admin_gate_hand_rolled  # noqa: E402


def _py(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


class TestAdminGateHandRolled:
    def test_clean_case_no_issues(self, tmp_path):
        _py(tmp_path, "products/a/backend/app/r.py", "def f(x):\n    return x\n")
        assert check_admin_gate_hand_rolled(repo_root=tmp_path) == []

    def test_missing_products_dir_is_clean(self, tmp_path):
        assert check_admin_gate_hand_rolled(repo_root=tmp_path) == []

    def test_in_tuple_flagged(self, tmp_path):
        _py(tmp_path, "products/a/backend/app/r.py", 'if role in ("admin", "owner"):\n    pass\n')
        issues = check_admin_gate_hand_rolled(repo_root=tmp_path)
        assert [i["severity"] for i in issues] == ["warning"]
        assert issues[0]["file"].endswith("r.py:1")

    def test_eq_and_not_in_flagged(self, tmp_path):
        _py(tmp_path, "products/a/backend/app/r.py",
            'a = user_role == "admin"\nb = org_role not in ["owner", "admin"]\n')
        assert len(check_admin_gate_hand_rolled(repo_root=tmp_path)) == 2

    def test_non_admin_role_not_flagged(self, tmp_path):
        _py(tmp_path, "products/a/backend/app/r.py", 'if role in ("member", "viewer"):\n    pass\n')
        assert check_admin_gate_hand_rolled(repo_root=tmp_path) == []

    def test_escape_marker_and_comments_skipped(self, tmp_path):
        _py(tmp_path, "products/a/backend/app/r.py",
            'x = role == "admin"  # admin-gate-ok: display label\n# role == "admin"\n')
        assert check_admin_gate_hand_rolled(repo_root=tmp_path) == []

    def test_tests_and_migrations_excluded(self, tmp_path):
        _py(tmp_path, "products/a/backend/tests/test_x.py", 'assert role == "admin"\n')
        _py(tmp_path, "products/a/backend/app/test_helper.py", 'assert role == "admin"\n')
        assert check_admin_gate_hand_rolled(repo_root=tmp_path) == []
