"""Tests for seed-inheritance-hardening Phase 5 keeper detectors.

Three new detectors + one behavioral tune:

  1. Control-plane classification (tune) — `check_seed_compliance` suppresses
     "Has own team.py / Layout.tsx" warnings for products in
     `CONTROL_PLANE_PRODUCTS` (today: `{"core"}`). Folds in the
     `keeper-control-plane-classification` backlog item.

  2. `check_frontend_entrypoint` — verifies the product's frontend entrypoint
     actually CALLS `createProductApp(...)` rather than rendering a raw React
     tree. Closes the gap where the App.tsx-scoped check never fires on core
     (core has no App.tsx).

  3. `check_out_of_contract_trees` — scans repo root for product-shaped
     directories living outside `products/*/`. Catches future `/adconnect/`-
     style strays.

All tests use `tmp_path` for isolation — no dependency on the live `products/`
state.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.compliance import (  # noqa: E402
    CONTROL_PLANE_PRODUCTS,
    check_frontend_entrypoint,
    check_out_of_contract_trees,
    check_seed_compliance,
)


# --- Shared helper ----------------------------------------------------------

def _mk_product(
    root: Path,
    name: str,
    *,
    main_py: str | None = None,
    requirements: str | None = None,
    vite_config: str | None = None,
    main_tsx: str | None = None,
    app_tsx: str | None = None,
    router_files: list[str] | None = None,
    layout_file_content: str | None = None,
) -> Path:
    """Build a product tree — enough for the compliance / entrypoint checks
    to operate. Every file is optional; omitted files simply don't exist."""
    p = root / name
    (p / "backend" / "app" / "routers").mkdir(parents=True, exist_ok=True)
    (p / "frontend" / "src" / "components" / "layout").mkdir(parents=True, exist_ok=True)

    if main_py is not None:
        (p / "backend" / "app" / "main.py").write_text(main_py)
    if requirements is not None:
        (p / "backend" / "requirements.txt").write_text(requirements)
    if vite_config is not None:
        (p / "frontend" / "vite.config.ts").write_text(vite_config)
    if main_tsx is not None:
        (p / "frontend" / "src" / "main.tsx").write_text(main_tsx)
    if app_tsx is not None:
        (p / "frontend" / "src" / "App.tsx").write_text(app_tsx)
    for fname in router_files or []:
        (p / "backend" / "app" / "routers" / fname).write_text("# stub\n")
    if layout_file_content is not None:
        (p / "frontend" / "src" / "components" / "layout" / "Layout.tsx").write_text(
            layout_file_content
        )
    return p


# --- 1. Control-plane classification ----------------------------------------

class TestControlPlaneClassification:
    def test_core_is_in_control_plane_set(self):
        """Core is the identity source — it OWNS team, notifications, etc.
        The classification set is the anchor for suppressing false positives."""
        assert "core" in CONTROL_PLANE_PRODUCTS

    def test_control_plane_product_own_team_router_not_flagged(self, tmp_path: Path):
        """Core has its own team.py — legitimate (it's the platform team
        authority). The old detector warned; v5 suppresses via classification."""
        main_py = (
            "from noctusai_seed import create_product_app\n"
            "app = create_product_app(name='Core', schema='public', settings=None,\n"
            "                         standard_routers=['health'])\n"
        )
        product = _mk_product(
            tmp_path, "core",  # name matches CONTROL_PLANE_PRODUCTS
            main_py=main_py,
            requirements="-e ../../seed/backend/framework\n-e ../../seed/backend/lib\n",
            router_files=["team.py", "notifications.py"],
        )
        issues = check_seed_compliance(product)
        assert not any("team.py" in i["file"] for i in issues), f"Got: {issues}"
        assert not any("notificacoes.py" in i["file"] for i in issues), f"Got: {issues}"

    def test_consumer_product_own_team_router_still_flagged(self, tmp_path: Path):
        """Consumer products should NOT own team.py (framework provides it).
        The control-plane suppression applies to {"core"} only."""
        main_py = (
            "from noctusai_seed import create_product_app\n"
            "app = create_product_app(name='Therapy', schema='therapy', settings=None,\n"
            "                         standard_routers=['health', 'team'])\n"
        )
        product = _mk_product(
            tmp_path, "consumer-with-team",  # name NOT in CONTROL_PLANE_PRODUCTS
            main_py=main_py,
            requirements="-e ../../seed/backend/framework\n-e ../../seed/backend/lib\n",
            router_files=["team.py"],
        )
        issues = check_seed_compliance(product)
        assert any("team.py" in i["file"] for i in issues)

    def test_control_plane_custom_layout_not_flagged(self, tmp_path: Path):
        """Core uses createProductApp({ Layout: CoreLayout }) — the Layout slot
        is a NAMED extension seam. Having a local Layout.tsx is expected; the
        high-severity "should use createProductLayout()" warning must be
        suppressed for control-plane products."""
        main_py = (
            "from noctusai_seed import create_product_app\n"
            "app = create_product_app(name='Core', schema='public', settings=None,\n"
            "                         standard_routers=['health'])\n"
        )
        app_tsx_content = (
            "import { createProductApp } from '@noctusai/seed';\n"
            "import { CoreLayout } from './components/layout/CoreLayout';\n"
            "const App = createProductApp({ Layout: CoreLayout });\n"
            "export default App;\n"
        )
        product = _mk_product(
            tmp_path, "core",
            main_py=main_py,
            requirements="-e ../../seed/backend/framework\n-e ../../seed/backend/lib\n",
            vite_config="import { createViteConfig } from 'seed'; export default createViteConfig();\n",
            app_tsx=app_tsx_content,
            layout_file_content="export const Layout = () => null;\n",
        )
        issues = check_seed_compliance(product)
        assert not any("Layout.tsx" in i["file"] for i in issues), f"Got: {issues}"


# --- 2. Frontend entrypoint detector ----------------------------------------

class TestFrontendEntrypoint:
    def test_direct_call_in_main_tsx_is_compliant(self, tmp_path: Path):
        """The core pattern: main.tsx directly calls createProductApp(...)."""
        product = _mk_product(
            tmp_path, "direct",
            main_tsx=(
                "import { createProductApp } from '@noctusai/seed';\n"
                "const App = createProductApp({ routes: [] });\n"
                "ReactDOM.createRoot(document.getElementById('root')!).render(<App />);\n"
            ),
        )
        assert check_frontend_entrypoint(product) == []

    def test_delegates_to_app_tsx_is_compliant(self, tmp_path: Path):
        """The therapy pattern: main.tsx → imports App from './App.tsx'
        which internally calls createProductApp."""
        product = _mk_product(
            tmp_path, "delegated",
            main_tsx=(
                "import App from './App.tsx';\n"
                "createRoot(document.getElementById('root')!).render(<App />);\n"
            ),
            app_tsx=(
                "import { createProductApp } from '@noctusai/seed';\n"
                "const App = createProductApp({ routes: [] });\n"
                "export default App;\n"
            ),
        )
        assert check_frontend_entrypoint(product) == []

    def test_raw_react_tree_is_flagged(self, tmp_path: Path):
        """Rendering a raw BrowserRouter/QueryClientProvider tree without
        going through createProductApp bypasses the framework."""
        product = _mk_product(
            tmp_path, "raw",
            main_tsx=(
                "import React from 'react';\n"
                "import ReactDOM from 'react-dom/client';\n"
                "import { BrowserRouter } from 'react-router-dom';\n"
                "import { QueryClientProvider } from '@tanstack/react-query';\n"
                "ReactDOM.createRoot(document.getElementById('root')!).render(\n"
                "  <BrowserRouter><App /></BrowserRouter>\n"
                ");\n"
            ),
        )
        issues = check_frontend_entrypoint(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"
        assert "createProductApp" in issues[0]["issue"]

    def test_imports_app_but_app_does_not_call_createproductapp(self, tmp_path: Path):
        """main.tsx imports ./App but App.tsx renders its own tree without
        createProductApp — still a bypass. Flag it."""
        product = _mk_product(
            tmp_path, "shallow-delegate",
            main_tsx=(
                "import App from './App.tsx';\n"
                "createRoot(document.getElementById('root')!).render(<App />);\n"
            ),
            app_tsx=(
                "import { BrowserRouter } from 'react-router-dom';\n"
                "export default function App() { return <BrowserRouter />; }\n"
            ),
        )
        issues = check_frontend_entrypoint(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"

    def test_missing_main_tsx_is_not_flagged(self, tmp_path: Path):
        """Backend-only products have no main.tsx — nothing to check."""
        product = tmp_path / "backend-only"
        product.mkdir()
        assert check_frontend_entrypoint(product) == []

    def test_import_style_variations_match(self, tmp_path: Path):
        """Accept both `'./App'` and `'./App.tsx'` import shapes."""
        for spec in ("'./App'", "'./App.tsx'", '"./App"', '"./App.tsx"'):
            product = _mk_product(
                tmp_path, f"variant-{hash(spec) & 0xffff:x}",
                main_tsx=f"import App from {spec};\ncreateRoot(null).render(<App />);\n",
                app_tsx="import { createProductApp } from '@noctusai/seed';\nconst App = createProductApp({});\nexport default App;\n",
            )
            assert check_frontend_entrypoint(product) == [], f"spec={spec}"


# --- 3. Out-of-contract trees detector --------------------------------------

class TestOutOfContractTrees:
    def _mk_repo(self, root: Path, dirs: dict[str, dict[str, str]]) -> Path:
        """Build a synthetic repo tree. `dirs` maps top-level dir name →
        {relative file path: content}. Creates parent dirs as needed."""
        for dname, files in dirs.items():
            for rel, content in files.items():
                target = root / dname / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
        return root

    def test_clean_repo_has_no_findings(self, tmp_path: Path):
        repo = self._mk_repo(tmp_path, {
            "products": {"seed/backend/app/main.py": "# ok"},
            "seed": {"backend/framework/noctusai_seed/__init__.py": "# framework\n"},
            "templates": {"product-seed/backend/app/main.py": "# template\n"},
            "projects": {"some-project/PROJECT.md": "# notes\n"},
        })
        assert check_out_of_contract_trees(repo) == []

    def test_detects_product_shaped_tree_at_root(self, tmp_path: Path):
        """A dir like `/adconnect/backend/app/main.py` at root is a stray
        product — flag it critical."""
        repo = self._mk_repo(tmp_path, {
            "products": {},
            "adconnect": {
                "backend/app/main.py": "# stray product",
                "frontend/src/main.tsx": "// stray frontend",
            },
        })
        issues = check_out_of_contract_trees(repo)
        assert len(issues) == 1
        assert issues[0]["file"] == "adconnect/"
        assert issues[0]["severity"] == "critical"
        assert "adconnect-seed-wiring" in issues[0]["issue"]
        assert "products/adconnect/" in issues[0]["issue"]

    def test_frontend_only_stray_is_also_flagged(self, tmp_path: Path):
        """A frontend-only (no backend) stray tree still counts."""
        repo = self._mk_repo(tmp_path, {
            "products": {},
            "legacy-ui": {"frontend/src/main.tsx": "// legacy"},
        })
        issues = check_out_of_contract_trees(repo)
        assert len(issues) == 1
        assert issues[0]["file"] == "legacy-ui/"
        assert "main.tsx" in issues[0]["issue"]

    def test_known_platform_dirs_excluded(self, tmp_path: Path):
        """`seed/`, `templates/`, `mcp/`, `KNOWLEDGE-BASE/`, `projects/` are
        legitimate non-product dirs at root. Must NOT be flagged even if
        they contain product-looking paths."""
        # templates contains a main.py as a scaffold — this must not trip it.
        repo = self._mk_repo(tmp_path, {
            "templates": {"product-seed/backend/app/main.py": "# template"},
            "seed": {"backend/framework/noctusai_seed/__init__.py": "# fw"},
            "products": {},
        })
        assert check_out_of_contract_trees(repo) == []

    def test_hidden_dirs_ignored(self, tmp_path: Path):
        """`.github/`, `.claude/`, `.venv/` etc. are infra directories —
        any shape inside them is out of scope for this detector."""
        repo = self._mk_repo(tmp_path, {
            ".github": {"backend/app/main.py": "# ci/cd surely"},
            "products": {},
        })
        assert check_out_of_contract_trees(repo) == []

    def test_multiple_strays_aggregate(self, tmp_path: Path):
        repo = self._mk_repo(tmp_path, {
            "products": {},
            "stray-a": {"backend/app/main.py": "# a"},
            "stray-b": {"frontend/src/main.tsx": "// b"},
        })
        issues = check_out_of_contract_trees(repo)
        assert len(issues) == 2
        files = {i["file"] for i in issues}
        assert files == {"stray-a/", "stray-b/"}

    def test_missing_repo_root_returns_empty(self, tmp_path: Path):
        """Defensive — if the supplied path doesn't exist, no crash."""
        ghost = tmp_path / "does-not-exist"
        assert check_out_of_contract_trees(ghost) == []

    def test_live_repo_is_clean(self):
        """Guard against regression: the live repo has zero out-of-contract
        trees after seed-inheritance-hardening Phase 2 reconciliation."""
        issues = check_out_of_contract_trees()
        assert issues == [], f"Live repo has strays: {issues}"
