"""Colocated regression test for `check_merge_drivers_have_contract_coverage` (meta-detector:
every keeper ships Test<CamelCase>). Red + green fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_merge_drivers_have_contract_coverage  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TEST_REL = "mcp/noctusai/tests/test_merge_driver_contract.py"


def _repo(tmp_path, attrs, specs):
    (tmp_path / ".gitattributes").write_text(attrs)
    if specs is not None:
        t = tmp_path / TEST_REL
        t.parent.mkdir(parents=True)
        t.write_text("SPECS = {\n" + "".join(f'    "{n}": Spec(path="x"),\n' for n in specs) + "}\n")
    return tmp_path


class TestMergeDriversHaveContractCoverage:
    def test_no_custom_driver_no_issues(self, tmp_path):
        assert check_merge_drivers_have_contract_coverage(repo_root=_repo(tmp_path, "a.ndjson merge=union\n", None)) == []

    def test_covered_drivers_clean(self, tmp_path):
        r = _repo(tmp_path, "A.md merge=kb-counts\nL.md merge=lgpd-warnings\nu merge=union\n", ["kb-counts", "lgpd-warnings"])
        assert check_merge_drivers_have_contract_coverage(repo_root=r) == []

    def test_driver_without_fixture_flagged(self, tmp_path):
        r = _repo(tmp_path, "A.md merge=kb-counts\nB.md merge=newdrv\n", ["kb-counts"])
        out = check_merge_drivers_have_contract_coverage(repo_root=r)
        assert len(out) == 1 and "newdrv" in out[0]["issue"] and out[0]["severity"] == "high"

    def test_missing_contract_test_flagged(self, tmp_path):
        out = check_merge_drivers_have_contract_coverage(repo_root=_repo(tmp_path, "A.md merge=kb-counts\n", None))
        assert len(out) == 1 and "missing" in out[0]["issue"]

    def test_live_repo_is_covered(self):
        assert check_merge_drivers_have_contract_coverage(repo_root=REPO) == []
