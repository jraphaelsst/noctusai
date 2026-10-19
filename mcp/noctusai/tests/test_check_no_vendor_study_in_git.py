"""`check_no_vendor_study_in_git` -- vendor study material stays out of git.

WHY (2026-10-19). 345 files of the CoreStudio and Lais reverse-engineering studies
(HTML dumps, their JS bundles, screenshots, XHR captures, data exports) were committed
under products/social-wiring/projects/. Owner decision: vendor-derived material lives
only in ~/Documents/repository/NoctusAI/_private-studies/<target>/, outside git; only
our own build specs are committed. Both directions are pinned.
-> KB § PATTERNS/common/app-reverse-engineering.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_no_vendor_study_in_git  # noqa: E402

P = "products/social-wiring/projects"


class TestCheckNoVendorStudyInGit:
    def test_flags_captures_tree(self):
        files = [f"{P}/core-studio/captures/pages/dashboard.html",
                 f"{P}/x/captures/xhr-2026/a.json"]
        assert len(check_no_vendor_study_in_git(files=files)) == 2

    def test_flags_exported_data_bundles(self):
        files = [f"{P}/core-studio/corestudio-data.json",
                 f"{P}/lais/tools/bubble-definition-dump.js",
                 "_private-studies/lais/js/a.js"]
        assert len(check_no_vendor_study_in_git(files=files)) == 3

    def test_allows_our_own_build_specs(self):
        files = [f"{P}/core-studio-build/specs/geracao-contract.md",
                 f"{P}/julia/specs/julia-agent-contract.md",
                 f"{P}/core-studio-build/DECISIONS.md",
                 "products/social-wiring/backend/app/modules/captures_service.py"]
        assert check_no_vendor_study_in_git(files=files) == []

    def test_issue_points_to_private_folder(self):
        issue = check_no_vendor_study_in_git(files=[f"{P}/a/captures/x.json"])[0]
        assert issue["severity"] == "high"
        assert "_private-studies" in issue["issue"]

    def test_real_tree_is_clean(self):
        """The regression guard: the 2026-10-19 move stays done."""
        issues = check_no_vendor_study_in_git()
        assert issues == [], [i["file"] for i in issues[:10]]
