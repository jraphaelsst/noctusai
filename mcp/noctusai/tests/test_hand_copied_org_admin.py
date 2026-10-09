"""Regression tests for `check_hand_copied_org_admin` (org-admin UX gate DRY keeper)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    _hcoa_scan_source,
    check_hand_copied_org_admin,
)

COPY = """const isAdmin =
    ssoCtx.isProductAdmin || ssoCtx.org.role === "owner" || ssoCtx.org.role === "admin";
"""


def _repo(tmp_path: Path, slug: str, rel: str, text: str) -> Path:
    (tmp_path / "deploy" / "fleet").mkdir(parents=True, exist_ok=True)
    (tmp_path / "deploy" / "fleet" / "active-scope.txt").write_text("awake\n", encoding="utf-8")
    f = tmp_path / "products" / slug / "frontend" / "src" / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    return tmp_path


class TestHandCopiedOrgAdmin:
    def test_canonical_copy_flagged_with_line(self):
        assert _hcoa_scan_source("// x\n" + COPY) == [3]

    def test_reversed_order_and_other_binding_flagged(self):
        src = 'return s.org.role === \'admin\' || s.org.role === \'owner\' || s.isProductAdmin;'
        assert _hcoa_scan_source(src) == [1]

    def test_helper_consumers_and_partial_checks_clean(self):
        assert _hcoa_scan_source("const a = isOrgAdmin(ctx) || ctx.org.role === \"dev\";") == []
        # owner/admin pair without isProductAdmin is a different gate (billing-style) — not this copy
        assert _hcoa_scan_source('const b = c.org.role === "owner" || c.org.role === "admin";') == []
        # the same role twice is not the owner/admin pair
        assert _hcoa_scan_source('x.isProductAdmin || x.org.role === "admin" || x.org.role === "admin";') == []

    def test_awake_product_copy_blocks(self, tmp_path):
        repo = _repo(tmp_path, "awake", "pages/P.tsx", COPY)
        issues = check_hand_copied_org_admin(repo_root=repo)
        assert [(i["product"], i["file"], i["severity"]) for i in issues] == [
            ("awake", "products/awake/frontend/src/pages/P.tsx:2", "high"),
        ]

    def test_asleep_product_and_tests_skipped(self, tmp_path):
        repo = _repo(tmp_path, "sleepy", "pages/P.tsx", COPY)
        _repo(repo, "awake", "pages/P.test.tsx", COPY)
        assert check_hand_copied_org_admin(repo_root=repo) == []
