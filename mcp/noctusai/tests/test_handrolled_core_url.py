"""Regression test for `check_handrolled_core_url` (core-url-routing-mandatory).

The mandatory core-URL routing rule: a product frontend MUST resolve core's
URL through the canonical seed getter `env.CORE_URL` / `env.CORE_API_URL`, never
hand-roll `import.meta.env.VITE_CORE_* || "<literal>"`. The detector flags any
hand-rolled site, with one carve-out: core's own same-origin `lib/api.ts`.

See KB § PATTERNS/frontend/core-url-routing.md + boundary-contract-tests.md B1.
All tests use `tmp_path` — no dependency on the live `products/` tree.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_handrolled_core_url  # noqa: E402


def _mk_page(root: Path, product: str, rel: str, body: str) -> Path:
    """Write a frontend source file under products/<product>/frontend/src/<rel>."""
    p = root / product / "frontend" / "src" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return root / product


_HANDROLLED_NAV = (
    'import { Link } from "react-router-dom";\n'
    'const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";\n'
)
_HANDROLLED_API = (
    'const CORE_API_URL = import.meta.env.VITE_CORE_API_URL || "http://localhost:8000";\n'
)
_CLEAN = (
    'import { env } from "@noctusai/lib";\n'
    'const CORE_URL = env.CORE_URL;\n'
)


class TestCheckHandrolledCoreUrl:
    def test_flags_handrolled_vite_core_url(self, tmp_path: Path) -> None:
        product = _mk_page(tmp_path, "daily-life", "pages/Login.tsx", _HANDROLLED_NAV)
        issues = check_handrolled_core_url(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert issues[0]["file"] == "frontend/src/pages/Login.tsx"
        assert issues[0]["product"] == "daily-life"

    def test_flags_handrolled_vite_core_api_url(self, tmp_path: Path) -> None:
        product = _mk_page(tmp_path, "erp", "pages/Configuracoes.tsx", _HANDROLLED_API)
        issues = check_handrolled_core_url(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"

    def test_clean_env_getter_not_flagged(self, tmp_path: Path) -> None:
        product = _mk_page(tmp_path, "personal-finance", "pages/Login.tsx", _CLEAN)
        assert check_handrolled_core_url(product) == []

    def test_core_api_ts_is_carved_out(self, tmp_path: Path) -> None:
        # core IS core — its own api client legitimately reads VITE_CORE_API_URL
        # with a window.location.origin fallback (same-origin self-reference).
        product = _mk_page(
            tmp_path, "core", "lib/api.ts",
            'const API_URL = import.meta.env.VITE_CORE_API_URL || window.location.origin;\n',
        )
        assert check_handrolled_core_url(product) == []

    def test_noncore_api_ts_still_flagged(self, tmp_path: Path) -> None:
        # The carve-out is core-only — a non-core product's lib/api.ts hand-roll
        # is still the bug.
        product = _mk_page(tmp_path, "adconnect", "lib/api.ts", _HANDROLLED_API)
        issues = check_handrolled_core_url(product)
        assert len(issues) == 1
        assert issues[0]["product"] == "adconnect"

    def test_comment_line_not_flagged(self, tmp_path: Path) -> None:
        product = _mk_page(
            tmp_path, "dev-team", "pages/Landing.tsx",
            "// legacy: import.meta.env.VITE_CORE_URL || 5173 (now env.CORE_URL)\n"
            "import { env } from \"@noctusai/lib\";\n"
            "const CORE_URL = env.CORE_URL;\n",
        )
        assert check_handrolled_core_url(product) == []

    def test_backend_only_product_skipped(self, tmp_path: Path) -> None:
        # No frontend/src → not a frontend-bearing product for this check.
        p = tmp_path / "backend-only"
        (p / "backend" / "app").mkdir(parents=True, exist_ok=True)
        assert check_handrolled_core_url(p) == []

    def test_multiple_sites_each_flagged(self, tmp_path: Path) -> None:
        product = _mk_page(tmp_path, "knowledge-extractor", "pages/Login.tsx", _HANDROLLED_NAV)
        _mk_page(tmp_path, "knowledge-extractor", "pages/Landing.tsx", _HANDROLLED_NAV)
        issues = check_handrolled_core_url(product)
        assert len(issues) == 2
        assert {i["file"] for i in issues} == {
            "frontend/src/pages/Login.tsx",
            "frontend/src/pages/Landing.tsx",
        }
