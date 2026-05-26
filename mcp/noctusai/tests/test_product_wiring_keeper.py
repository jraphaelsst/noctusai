"""Regression tests for the product-internal-wiring static-leg keeper detectors.

The three detectors (`check_fe_route_missing` / `check_name_on_nome_select` /
`check_promise_all_shared_catch`) codify the STATIC legs of the
product-internal-wiring audit (`KB § PATTERNS/frontend/product-internal-wiring.md`
legs 2/4/5) as Stage-4 keeper detectors. Each reuses the EXACT shared predicate
already shipped in `tools/noctus/dev/scan_wiring.py` (one predicate, two
surfaces — the `noctus.dev.scan_wiring` MCP tool + these keepers).

Per `KB § PATTERNS/compliance/testing.md § Regression-test-the-detector`, each detector
pins its true-positive (fires) + false-positive (silent) shapes. All tests use
`tmp_path` — no dependency on the live `products/` tree (mirrors the sibling
`test_handrolled_core_url.py` fixture style: `tmp_path/<slug>/...`, no
`products/` layer).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_fe_route_missing,
    check_name_on_nome_select,
    check_promise_all_shared_catch,
)


def _mk_file(root: Path, product: str, rel: str, body: str) -> Path:
    """Write products/<product>/<rel>; return the product dir (tmp_path/<product>)."""
    p = root / product / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return root / product


# Canonical backend wiring used by the Leg-A positive/negative fixtures: a
# plans router with a collection GET + a dynamic PATCH, mounted at /api/plans.
_ROUTER_PY = (
    "from fastapi import APIRouter\n"
    "router = APIRouter()\n"
    "@router.get('/')\n"
    "def list_plans():\n    return []\n"
    "@router.patch('/{plan_id}')\n"
    "def update_plan(plan_id: str):\n    return {}\n"
)
_MAIN_PY = (
    "from fastapi import FastAPI\n"
    "from app.routers import plans\n"
    "app = FastAPI()\n"
    "app.include_router(plans.router, prefix='/api/plans')\n"
)


# ---------------------------------------------------------------------------
# Leg A — check_fe_route_missing
# ---------------------------------------------------------------------------

class TestCheckFeRouteMissing:
    def _backend(self, root: Path, product: str) -> Path:
        _mk_file(root, product, "backend/app/main.py", _MAIN_PY)
        return _mk_file(root, product, "backend/app/routers/plans.py", _ROUTER_PY)

    def test_matched_route_not_flagged(self, tmp_path: Path) -> None:
        self._backend(tmp_path, "core")
        product = _mk_file(
            tmp_path, "core", "frontend/src/pages/Plans.tsx",
            "const all = await api.get('/api/plans');\n"
            "await api.patch(`/api/plans/${planId}`, body);\n",
        )
        assert check_fe_route_missing(product) == []

    def test_missing_route_flagged_high(self, tmp_path: Path) -> None:
        self._backend(tmp_path, "core")
        product = _mk_file(
            tmp_path, "core", "frontend/src/pages/Plans.tsx",
            "const x = await api.get('/api/subscriptions');\n",
        )
        issues = check_fe_route_missing(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert issues[0]["product"] == "core"
        assert "subscriptions" in issues[0]["issue"]
        assert issues[0]["file"].endswith("Plans.tsx")

    def test_wrong_method_flagged(self, tmp_path: Path) -> None:
        self._backend(tmp_path, "core")
        product = _mk_file(
            tmp_path, "core", "frontend/src/pages/Plans.tsx",
            "await api.delete('/api/plans');\n",
        )
        issues = check_fe_route_missing(product)
        assert len(issues) == 1
        assert "DELETE" in issues[0]["issue"]

    def test_backend_only_product_skipped(self, tmp_path: Path) -> None:
        # No frontend/ → no FE surfaces to wire.
        product = _mk_file(tmp_path, "backend-only", "backend/app/main.py", _MAIN_PY)
        assert check_fe_route_missing(product) == []


# ---------------------------------------------------------------------------
# Leg B — check_name_on_nome_select
# ---------------------------------------------------------------------------

class TestCheckNameOnNomeSelect:
    def test_name_on_plans_flagged_high(self, tmp_path: Path) -> None:
        product = _mk_file(
            tmp_path, "core", "backend/app/services/subscriptions.py",
            "rows = sb.table('licenses').select('id, plans(name)').execute()\n",
        )
        issues = check_name_on_nome_select(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert issues[0]["product"] == "core"
        assert "plans" in issues[0]["issue"]
        assert "nome" in issues[0]["issue"]

    def test_inner_embed_organizations_flagged(self, tmp_path: Path) -> None:
        product = _mk_file(
            tmp_path, "core", "backend/app/services/sub.py",
            "q = sb.table('licenses').select('*, organizations!inner(name)')\n",
        )
        issues = check_name_on_nome_select(product)
        assert len(issues) == 1
        assert "organizations" in issues[0]["issue"]

    def test_nome_select_not_flagged(self, tmp_path: Path) -> None:
        product = _mk_file(
            tmp_path, "core", "backend/app/services/subscriptions.py",
            "rows = sb.table('licenses').select('id, plans(nome)').execute()\n",
        )
        assert check_name_on_nome_select(product) == []

    def test_name_on_non_nome_table_not_flagged(self, tmp_path: Path) -> None:
        product = _mk_file(
            tmp_path, "core", "backend/app/services/svc.py",
            "rows = sb.table('x').select('users(name)').execute()\n",
        )
        assert check_name_on_nome_select(product) == []


# ---------------------------------------------------------------------------
# Leg C — check_promise_all_shared_catch
# ---------------------------------------------------------------------------

class TestCheckPromiseAllSharedCatch:
    _SHARED_CATCH = (
        "async function load() {\n"
        "  try {\n"
        "    const [a, b, c] = await Promise.all([\n"
        "      api.get('/api/stats'),\n"
        "      api.get('/api/orgs'),\n"
        "      api.get('/api/products'),\n"
        "    ]);\n"
        "  } catch (e) {\n"
        "    setAll(0);\n"
        "  }\n"
        "}\n"
    )
    _PER_ELEMENT_CATCH = (
        "async function load() {\n"
        "  try {\n"
        "    const [a, b] = await Promise.all([\n"
        "      api.get('/api/stats').catch(() => ({})),\n"
        "      api.get('/api/orgs').catch(() => []),\n"
        "    ]);\n"
        "  } catch (e) {\n"
        "    notify(e);\n"
        "  }\n"
        "}\n"
    )
    # Leg-4 precision: ONE deliberate primary (failure SHOULD propagate to the
    # shared catch → logout) + degrading aux already guarded. Mixed ⇒ NOT the
    # all-zeros bug ⇒ NOT flagged.
    _MIXED_PRIMARY_PLUS_AUX = (
        "async function load() {\n"
        "  try {\n"
        "    const [me, stats, orgs] = await Promise.all([\n"
        "      api.get('/api/me'),\n"
        "      api.get('/api/stats').catch(() => ({})),\n"
        "      api.get('/api/orgs').catch(() => []),\n"
        "    ]);\n"
        "  } catch (e) {\n"
        "    logoutAndRedirect();\n"
        "  }\n"
        "}\n"
    )

    def test_shared_catch_flagged_warning(self, tmp_path: Path) -> None:
        # Pure shared-catch (every element bare) → FLAG.
        product = _mk_file(
            tmp_path, "core", "frontend/src/pages/Dashboard.tsx", self._SHARED_CATCH
        )
        issues = check_promise_all_shared_catch(product)
        assert len(issues) == 1
        # warning severity → does NOT enter the high/critical regression baseline.
        assert issues[0]["severity"] == "warning"
        assert issues[0]["product"] == "core"
        assert issues[0]["file"].endswith("Dashboard.tsx")

    def test_per_element_catch_not_flagged(self, tmp_path: Path) -> None:
        # All elements guarded → NOT flagged.
        product = _mk_file(
            tmp_path, "core", "frontend/src/pages/Dashboard.tsx",
            self._PER_ELEMENT_CATCH,
        )
        assert check_promise_all_shared_catch(product) == []

    def test_mixed_primary_plus_aux_not_flagged(self, tmp_path: Path) -> None:
        # Leg-4 precision: ≥1 element guarded → deliberate primary+aux, NOT the
        # all-zeros bug → NOT flagged (the keeper must agree with the analyzer).
        product = _mk_file(
            tmp_path, "core", "frontend/src/pages/Dashboard.tsx",
            self._MIXED_PRIMARY_PLUS_AUX,
        )
        assert check_promise_all_shared_catch(product) == []

    def test_backend_only_product_skipped(self, tmp_path: Path) -> None:
        product = _mk_file(tmp_path, "backend-only", "backend/app/main.py", _MAIN_PY)
        assert check_promise_all_shared_catch(product) == []


# ---------------------------------------------------------------------------
# DRY proof — the keeper detectors reuse the SAME scan_wiring predicates.
# ---------------------------------------------------------------------------

class TestKeeperReusesScanWiringPredicate:
    def test_keeper_findings_match_scan_wiring_tool(self, tmp_path: Path) -> None:
        """The keeper + the `noctus.dev.scan_wiring` tool agree on the same tree
        (proves they share the predicate, not two divergent copies)."""
        from tools.noctus.dev.scan_wiring import scan_wiring

        # Build a real `products/<slug>` tree so scan_wiring() resolves it.
        repo = tmp_path
        slug = "core"
        files = {
            "backend/app/main.py": _MAIN_PY,
            "backend/app/routers/plans.py": _ROUTER_PY,
            "backend/app/services/s.py": "sb.table('x').select('plans(name)')\n",
            "frontend/src/pages/P.tsx": (
                "const x = await api.get('/api/missing');\n"
                "try {\n"
                "  await Promise.all([api.get('/api/a'), api.get('/api/b')]);\n"
                "} catch (e) { setZero(); }\n"
            ),
        }
        for rel, body in files.items():
            p = repo / "products" / slug / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)

        product_path = repo / "products" / slug
        tool = scan_wiring(slug, repo_root=repo)

        keeper_missing = check_fe_route_missing(product_path)
        keeper_nome = check_name_on_nome_select(product_path)
        keeper_catch = check_promise_all_shared_catch(product_path)

        assert len(keeper_missing) == tool["totals"]["missing_routes"] >= 1
        assert len(keeper_nome) == tool["totals"]["name_on_nome"] == 1
        assert len(keeper_catch) == tool["totals"]["shared_catch_promise_all"] == 1
