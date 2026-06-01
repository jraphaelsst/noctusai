"""Regression tests for check_consent_routes_mounted.

Five test cases:
  1. seed_clean_passes          — correct seed app.tsx + index.ts → clean
  2. missing_route_mount_fails  — app.tsx missing a /consent* mount → blocked
  3. missing_page_import_fails  — app.tsx missing a page import → blocked
  4. missing_index_export_fails — index.ts missing a page export → blocked
  5. product_shadow_fails       — product-local ConsentHubPage declaration → blocked

KB § PATTERNS/frontend/consent-routes-mandate.md
"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_consent_routes_mounted

# ── helpers ──────────────────────────────────────────────────────────────────

_GOOD_APP_TSX = """\
import { ConsentHubPage } from "./pages/consent/ConsentHubPage";
import { PrivacyPolicyPage } from "./pages/consent/PrivacyPolicyPage";
import { TermsOfUsePage } from "./pages/consent/TermsOfUsePage";

function AppRoutes() {
  return (
    <>
      <Route path="/consent" element={<ConsentHubPage />} />
      <Route path="/consent/privacy-policy" element={<PrivacyPolicyPage />} />
      <Route path="/consent/terms-of-use" element={<TermsOfUsePage />} />
    </>
  );
}
"""

_GOOD_INDEX_TS = """\
export { ConsentHubPage } from './pages/consent/ConsentHubPage';
export { PrivacyPolicyPage } from './pages/consent/PrivacyPolicyPage';
export { TermsOfUsePage } from './pages/consent/TermsOfUsePage';
export { CONSENT_META, CONSENT_DOCS, PRIVACY_POLICY, TERMS_OF_USE } from './content/consent';
export type { ConsentDoc, DocSection, DocBlock } from './content/consent';
"""


def _make_repo(tmp: Path) -> Path:
    """Scaffold a minimal fake-repo layout under `tmp`."""
    seed_src = tmp / "seed" / "framework" / "frontend" / "src"
    seed_src.mkdir(parents=True, exist_ok=True)
    (tmp / "products").mkdir(parents=True, exist_ok=True)
    return tmp


def _write_seed(repo: Path, app_content: str, index_content: str) -> None:
    seed_src = repo / "seed" / "framework" / "frontend" / "src"
    (seed_src / "app.tsx").write_text(app_content, encoding="utf-8")
    (seed_src / "index.ts").write_text(index_content, encoding="utf-8")


def _product_file(repo: Path, slug: str, rel: str, content: str) -> Path:
    target = repo / "products" / slug / "frontend" / "src" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


# ── test cases ────────────────────────────────────────────────────────────────


class TestConsentRoutesMandatePasses:
    """A correct seed with no product shadows must report zero issues."""

    def test_clean_seed_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _write_seed(repo, _GOOD_APP_TSX, _GOOD_INDEX_TS)
            issues = check_consent_routes_mounted(repo_root=repo)
        assert not issues, f"Expected no issues; got {issues}"

    def test_product_importing_consent_page_is_clean(self) -> None:
        """A product IMPORTING a consent component is fine (consuming = correct)."""
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _write_seed(repo, _GOOD_APP_TSX, _GOOD_INDEX_TS)
            _product_file(
                repo,
                "some-product",
                "pages/SomePage.tsx",
                'import { ConsentHubPage } from "@noctusai/lib";\n'
                "// this is a consumer, not a re-implementer\n",
            )
            issues = check_consent_routes_mounted(repo_root=repo)
        assert not issues, f"Import-only should be clean; got {issues}"


class TestMissingRouteMountFails:
    """Missing route mounts in app.tsx must be flagged."""

    def test_missing_consent_hub_mount(self) -> None:
        app_missing_hub = _GOOD_APP_TSX.replace(
            '<Route path="/consent" element={<ConsentHubPage />} />\n', ""
        )
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _write_seed(repo, app_missing_hub, _GOOD_INDEX_TS)
            issues = check_consent_routes_mounted(repo_root=repo)
        route_issues = [
            i for i in issues if 'path="/consent"' in i["issue"]
        ]
        assert route_issues, "Missing /consent mount must be flagged"
        assert all(i["severity"] == "high" for i in route_issues)

    def test_missing_privacy_policy_mount(self) -> None:
        app_missing = _GOOD_APP_TSX.replace(
            '<Route path="/consent/privacy-policy" element={<PrivacyPolicyPage />} />\n', ""
        )
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _write_seed(repo, app_missing, _GOOD_INDEX_TS)
            issues = check_consent_routes_mounted(repo_root=repo)
        route_issues = [
            i for i in issues if "privacy-policy" in i["issue"]
        ]
        assert route_issues, "Missing /consent/privacy-policy mount must be flagged"

    def test_missing_terms_of_use_mount(self) -> None:
        app_missing = _GOOD_APP_TSX.replace(
            '<Route path="/consent/terms-of-use" element={<TermsOfUsePage />} />\n', ""
        )
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _write_seed(repo, app_missing, _GOOD_INDEX_TS)
            issues = check_consent_routes_mounted(repo_root=repo)
        route_issues = [
            i for i in issues if "terms-of-use" in i["issue"]
        ]
        assert route_issues, "Missing /consent/terms-of-use mount must be flagged"


class TestMissingPageImportFails:
    """Missing page component imports in app.tsx must be flagged."""

    def test_missing_consent_hub_import(self) -> None:
        app_no_import = _GOOD_APP_TSX.replace(
            'import { ConsentHubPage } from "./pages/consent/ConsentHubPage";\n', ""
        )
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _write_seed(repo, app_no_import, _GOOD_INDEX_TS)
            issues = check_consent_routes_mounted(repo_root=repo)
        import_issues = [
            i for i in issues if "ConsentHubPage" in i["issue"]
        ]
        assert import_issues, "Missing ConsentHubPage import must be flagged"
        assert all(i["severity"] == "high" for i in import_issues)


class TestMissingIndexExportFails:
    """Missing exports from seed index.ts must be flagged."""

    def test_missing_consent_hub_export(self) -> None:
        index_missing = _GOOD_INDEX_TS.replace(
            "export { ConsentHubPage } from './pages/consent/ConsentHubPage';\n", ""
        )
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _write_seed(repo, _GOOD_APP_TSX, index_missing)
            issues = check_consent_routes_mounted(repo_root=repo)
        export_issues = [
            i for i in issues if "ConsentHubPage" in i["issue"] and "index.ts" in i["file"]
        ]
        assert export_issues, "Missing ConsentHubPage export from index.ts must be flagged"

    def test_missing_content_module_export(self) -> None:
        # Remove ALL lines referencing content/consent so the path check fires.
        index_missing = "\n".join(
            line for line in _GOOD_INDEX_TS.splitlines()
            if "content/consent" not in line
        )
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _write_seed(repo, _GOOD_APP_TSX, index_missing)
            issues = check_consent_routes_mounted(repo_root=repo)
        export_issues = [
            i for i in issues if "content/consent" in i["issue"] and "index.ts" in i["file"]
        ]
        assert export_issues, "Missing consent content module path in index.ts must be flagged"


class TestProductShadowFails:
    """Product-local declarations of consent page components must be flagged."""

    def test_product_local_consent_hub_declaration_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _write_seed(repo, _GOOD_APP_TSX, _GOOD_INDEX_TS)
            _product_file(
                repo,
                "bad-product",
                "pages/ConsentHub.tsx",
                "export function ConsentHubPage() {\n"
                "  return <div>My custom consent hub</div>;\n"
                "}\n",
            )
            issues = check_consent_routes_mounted(repo_root=repo)
        shadow_issues = [
            i for i in issues
            if "ConsentHubPage" in i["issue"] and i["product"] == "bad-product"
        ]
        assert shadow_issues, "Product-local ConsentHubPage declaration must be flagged"
        assert all(i["severity"] == "high" for i in shadow_issues)

    def test_product_local_privacy_policy_declaration_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _write_seed(repo, _GOOD_APP_TSX, _GOOD_INDEX_TS)
            _product_file(
                repo,
                "another-product",
                "pages/Privacy.tsx",
                "const PrivacyPolicyPage = () => <div>Local policy</div>;\n"
                "export default PrivacyPolicyPage;\n",
            )
            issues = check_consent_routes_mounted(repo_root=repo)
        shadow_issues = [
            i for i in issues
            if "PrivacyPolicyPage" in i["issue"] and i["product"] == "another-product"
        ]
        assert shadow_issues, "Product-local PrivacyPolicyPage declaration must be flagged"

    def test_product_local_terms_declaration_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _write_seed(repo, _GOOD_APP_TSX, _GOOD_INDEX_TS)
            _product_file(
                repo,
                "yet-another",
                "pages/Terms.tsx",
                "export const TermsOfUsePage = () => <p>My terms</p>;\n",
            )
            issues = check_consent_routes_mounted(repo_root=repo)
        shadow_issues = [
            i for i in issues
            if "TermsOfUsePage" in i["issue"] and i["product"] == "yet-another"
        ]
        assert shadow_issues, "Product-local TermsOfUsePage declaration must be flagged"
