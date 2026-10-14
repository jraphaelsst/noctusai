"""`noctus.dev.scaffold_product(overlay="erp")` -- the ERP overlay on top of templates/product-seed."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import scaffold as scaffold_module
from tools.noctus.dev.scaffold import scaffold_product
from tools.noctus.dev.scaffold_overlay import OverlayError, load_overlay, organ_render_order

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))
sys.path.insert(0, str(REPO_ROOT / "seed" / "framework" / "backend"))
TEMPLATE = REPO_ROOT / "templates" / "product-seed"
OVERLAY = REPO_ROOT / "templates" / "product-erp"

from noctusai_lib.testing.organs import expected_organ_migration  # noqa: E402
from noctusai_seed.organs import ORGAN_REGISTRY  # noqa: E402

SLUG, SCHEMA = "acme-erp", "acme_erp"


@pytest.fixture(autouse=True)
def _stub_llm_rewrite(monkeypatch):
    async def _no_op(template_content, **_kwargs):
        return None

    monkeypatch.setattr(scaffold_module, "llm_rewrite_file_content", _no_op)


@pytest.fixture
def scaffolded(tmp_path):
    products = tmp_path / "products"
    (products / "core" / "backend" / "migrations").mkdir(parents=True)
    result = scaffold_product(
        "Acme ERP", SLUG, SCHEMA, 8097, 8197, "Zap",
        brief={}, products_dir=products, template_dir=TEMPLATE, overlay="erp",
    )
    assert result.get("created") is True, result
    return tmp_path, products / SLUG, result


def _numbered(target: Path) -> dict[str, int]:
    return {p.name: int(re.match(r"(\d+)_", p.name).group(1)) for p in (target / "backend" / "migrations").glob("*.sql")}


class TestErpOverlay:
    def test_overlay_files_present_and_base_not_duplicated(self, scaffolded):
        _tmp, target, result = scaffolded
        for rel in (
            "backend/app/erp_organs.py", "backend/app/erp_scheduler.py", "backend/tests/test_erp_wiring.py",
            "frontend/src/lib/erpHooks.ts", "frontend/src/pages/Dashboard.tsx", "frontend/src/pages/Estoque.tsx",
            "frontend/src/pages/Compras.tsx", "frontend/src/pages/Contratos.tsx", "frontend/src/pages/Orcamentos.tsx",
            "frontend/src/pages/Parceiros.tsx", "frontend/src/pages/Itens.tsx",
        ):
            assert (target / rel).is_file(), rel
        assert not (target / "overlay.json").exists() and not (target / "OVERLAY.md").exists()
        # the base is still the base (finance mount + team page come from product-seed, not from the overlay)
        assert (target / "backend" / "migrations" / "012_finance.sql").is_file()
        assert (target / "frontend" / "src" / "pages" / "Financeiro.tsx").is_file()
        assert "frontend/src/pages/Financeiro.tsx" not in result["overlay"]["files"]

    def test_migrations_follow_requires_order_and_equal_the_generators(self, scaffolded):
        _tmp, target, result = scaffolded
        numbers = _numbered(target)
        base_max = numbers["013_status_pagina_financeiro.sql"]  # the last base migration
        by_organ = {o: next(n for name, n in numbers.items() if name.endswith(f"_{o}.sql")) for o in result["overlay"]["organs"]}
        by_organ["finance"] = numbers["012_finance.sql"]
        assert all(by_organ[o] > base_max for o in result["overlay"]["organs"])
        for organ, number in by_organ.items():
            for dep in ORGAN_REGISTRY[organ].requires:
                assert by_organ[dep] < number, f"{organ} must be numbered after {dep}"
        for organ in result["overlay"]["organs"]:
            path = next((target / "backend" / "migrations").glob(f"*_{organ}.sql"))
            assert path.read_text(encoding="utf-8") == expected_organ_migration(organ, SCHEMA, 1)
        status = next((target / "backend" / "migrations").glob("*_status_pagina_erp.sql"))
        assert numbers[status.name] == max(numbers.values())
        for route in ("parceiros", "itens", "estoque", "compras", "contratos", "orcamentos"):
            assert f"('{route}', 'producao')" in status.read_text(encoding="utf-8")

    def test_placeholders_resolved_and_anchored_patches_applied(self, scaffolded):
        _tmp, target, _result = scaffolded
        for f in target.rglob("*"):
            if f.is_file() and f.suffix in {".py", ".ts", ".tsx", ".sql", ".json"}:
                text = f.read_text(encoding="utf-8")
                assert not re.search(r"\{\{(PRODUCT_\w+|SCHEMA_NAME|BACKEND_PORT|FRONTEND_PORT)\}\}", text), f
        main = (target / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        assert "organs=ERP_ORGANS" in main and "mount_finance" not in main and "configure_scheduler()" in main
        assert f'SCHEMA = "{SCHEMA}"' in (target / "backend" / "app" / "erp_organs.py").read_text(encoding="utf-8")
        app = (target / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        assert app.count('href: "/orcamentos"') == 2  # NAV_GROUPS + NAV_FALLBACK
        assert '{ path: "/contratos", component: Contratos }' in app and "Contact" in app.split("lucide-react")[0]

    def test_registered_deploy_scope_dev_only(self, scaffolded):
        tmp, _target, result = scaffolded
        assert result["overlay"]["deploy_scope"] == "dev"
        sql = Path(result["seed_row_migration"]["path"]).read_text(encoding="utf-8")
        assert "deploy_scope" in sql and "'dev'" in sql and "'live'" not in sql
        assert any("dev only" in step for step in result["next_steps"])

    def test_scaffolded_backend_imports_and_its_wiring_tests_pass(self, scaffolded):
        tmp, target, _result = scaffolded
        (tmp / "seed").symlink_to(REPO_ROOT / "seed")  # the product conftest finds the seed at <root>/seed
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_erp_wiring.py", "-q", "-p", "no:cacheprovider"],
            cwd=target / "backend", capture_output=True, text=True, timeout=240,
        )
        assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-1500:]


class TestOverlayRefusals:
    def test_unknown_overlay_is_refused_and_creates_nothing(self, tmp_path):
        result = scaffold_product("X", "x-prod", "x_prod", 8096, 8196, brief={}, products_dir=tmp_path, template_dir=TEMPLATE, overlay="nope")
        assert "not found" in result["error"]
        assert not (tmp_path / "x-prod").exists()

    def test_base_drift_fails_loudly_and_removes_the_product(self, tmp_path):
        drifted = tmp_path / "templates"
        shutil.copytree(TEMPLATE, drifted / "product-seed")
        shutil.copytree(OVERLAY, drifted / "product-erp")
        main = drifted / "product-seed" / "backend" / "app" / "main.py"
        main.write_text(main.read_text(encoding="utf-8").replace("organs=[", "organs_=["), encoding="utf-8")
        products = tmp_path / "products"
        result = scaffold_product("X", "x-prod", "x_prod", 8096, 8196, brief={}, products_dir=products,
                                  template_dir=drifted / "product-seed", overlay="erp")
        assert "anchor not found" in result["error"]
        assert not (products / "x-prod").exists()

    def test_undeclared_collision_is_refused(self, tmp_path):
        overlay = tmp_path / "product-erp"
        shutil.copytree(OVERLAY, overlay)
        manifest = overlay / "overlay.json"
        manifest.write_text(manifest.read_text(encoding="utf-8").replace('"replaces": ["frontend/src/pages/Dashboard.tsx"]', '"replaces": []'))
        result = scaffold_product("X", "x-prod", "x_prod", 8096, 8196, brief={}, products_dir=tmp_path / "products",
                                  template_dir=TEMPLATE, overlay="erp", overlay_dir=overlay)
        assert "not declared in `replaces`" in result["error"]
        assert not (tmp_path / "products" / "x-prod").exists()

    def test_manifest_cannot_target_prod(self, tmp_path):
        overlay = tmp_path / "product-erp"
        shutil.copytree(OVERLAY, overlay)
        manifest = overlay / "overlay.json"
        manifest.write_text(manifest.read_text(encoding="utf-8").replace('"deploy_scope": "dev"', '"deploy_scope": "live"'))
        with pytest.raises(OverlayError, match="deploy_scope='dev' only"):
            load_overlay(overlay)

    def test_render_order_is_topological_and_rejects_unprovided_dependencies(self):
        order = organ_render_order(["quotes", "inventory", "items", "parties"], [])
        assert order.index("items") < order.index("inventory") and order.index("parties") < order.index("quotes")
        with pytest.raises(OverlayError, match="requires"):
            organ_render_order(["purchasing"], [])  # needs parties/items/inventory/finance
