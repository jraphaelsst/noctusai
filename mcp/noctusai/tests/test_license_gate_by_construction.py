"""Colocated regression test for `check_license_gate_by_construction` (meta-detector: every
keeper ships Test<CamelCase>)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    _lgc_scan_source,
    check_license_gate_by_construction,
)


def _product(tmp_path: Path, name: str, code: str) -> Path:
    f = tmp_path / "products" / name / "backend" / "app" / "dependencies.py"
    f.parent.mkdir(parents=True)
    f.write_text(code, encoding="utf-8")
    (tmp_path / "deploy" / "fleet").mkdir(parents=True, exist_ok=True)
    (tmp_path / "deploy" / "fleet" / "active-scope.txt").write_text(f"{name}\n", encoding="utf-8")
    return f


class TestLicenseGateByConstruction:
    def test_clean_case_no_issues(self, tmp_path):
        assert check_license_gate_by_construction(paths=[], repo_root=tmp_path) == []

    def test_factory_consumer_is_clean(self, tmp_path):
        _product(tmp_path, "acme", "from x import make_get_current_user_org\n"
                                    "get_current_user_org = make_get_current_user_org(a, b)\n")
        assert check_license_gate_by_construction(repo_root=tmp_path) == []

    def test_hand_rolled_org_dependency_flagged(self, tmp_path):
        _product(tmp_path, "acme", "async def get_current_user_org(user):\n    return user.user_metadata['org_id']\n")
        [issue] = check_license_gate_by_construction(repo_root=tmp_path)
        assert issue["severity"] == "critical" and "hand-rolled org dependency" in issue["issue"]

    def test_opt_out_flagged(self, tmp_path):
        _product(tmp_path, "acme", "from x import make_get_current_user_org\n"
                                    "dep = make_get_current_user_org(a, b, enforce_license=False)\n")
        [issue] = check_license_gate_by_construction(repo_root=tmp_path)
        assert "opts out" in issue["issue"]

    def test_own_gate_configuration_flagged(self, tmp_path):
        _product(tmp_path, "acme", "configure_license_gate('acme', None)\n")
        assert len(check_license_gate_by_construction(repo_root=tmp_path)) == 1

    def test_admin_branch_bypassing_license_flagged_anywhere(self):
        src = "def f(role, org):\n    if role == 'admin':\n        return True\n    else:\n        enforce_license(org, role)\n"
        [issue] = _lgc_scan_source(src, "seed/x.py", "<seed>", is_product=False)
        assert "admin" in issue["issue"]

    def test_admin_branch_without_license_call_is_fine(self):
        src = "def f(role):\n    if role == 'admin':\n        return 1\n"
        assert _lgc_scan_source(src, "seed/x.py", "<seed>", is_product=False) == []

    def test_product_using_ungated_dep_flagged(self, tmp_path):
        _product(tmp_path, "acme", "from x import make_get_current_user_ungated\n"
                                    "get_current_user = make_get_current_user_ungated(lambda: None)\n")
        issues = check_license_gate_by_construction(repo_root=tmp_path)
        assert any("UNGATED" in i["issue"] for i in issues)

    def test_store_is_no_longer_exempt(self, tmp_path):
        _product(tmp_path, "store", "async def get_current_user_org(user):\n    return 1\n")
        assert len(check_license_gate_by_construction(repo_root=tmp_path)) == 1

    def test_seed_file_outside_allowlist_using_ungated_flagged(self, tmp_path):
        f = tmp_path / "seed" / "framework" / "backend" / "noctusai_seed" / "x_router.py"
        f.parent.mkdir(parents=True)
        f.write_text("def f(deps):\n    return deps.get_current_user_ungated\n", encoding="utf-8")
        issues = check_license_gate_by_construction(repo_root=tmp_path)
        assert any("UNGATED" in i["issue"] for i in issues)

    def test_missing_seed_wiring_flagged(self, tmp_path):
        f = tmp_path / "seed" / "framework" / "backend" / "noctusai_seed" / "app.py"
        f.parent.mkdir(parents=True)
        f.write_text("# no gate here\n", encoding="utf-8")
        [issue] = check_license_gate_by_construction(repo_root=tmp_path)
        assert "wiring" in issue["issue"]

    def test_real_repo_is_clean(self):
        root = Path(__file__).resolve().parents[3]
        assert check_license_gate_by_construction(repo_root=root) == []
