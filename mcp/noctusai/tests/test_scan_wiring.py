"""Tests for `tools/noctus/dev/scan_wiring.py` — the static wiring-check.

Each leg gets a positive (flag) + negative (no flag) case, exercised over a
tmp_path mini-product tree (mirrors `test_recurrence.py`'s fixture style).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.scan_wiring import (
    scan_wiring,
    _normalize_path,
    _NOME_TABLES,
)


# ---------------------------------------------------------------------------
# Mini-product tree builder
# ---------------------------------------------------------------------------

def _mk_product(tmp_path: Path, slug: str, files: dict[str, str]) -> Path:
    """Create `products/<slug>/<rel>` files from `{rel: content}`; return repo root."""
    for rel, content in files.items():
        full = tmp_path / "products" / slug / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
    return tmp_path


# ---------------------------------------------------------------------------
# Honest error
# ---------------------------------------------------------------------------

class TestHonestError:
    def test_missing_product_returns_typed_error(self, tmp_path: Path):
        result = scan_wiring("nonexistent", repo_root=tmp_path)
        assert result["ok"] is False
        assert "does not exist" in result["error"]


# ---------------------------------------------------------------------------
# Leg A — FE-endpoint → backend-route existence
# ---------------------------------------------------------------------------

class TestLegARouteExistence:
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

    def test_matched_route_not_flagged(self, tmp_path: Path):
        repo = _mk_product(tmp_path, "core", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/plans.py": self._ROUTER_PY,
            # FE calls both the collection GET and the dynamic PATCH.
            "frontend/src/pages/Plans.tsx": (
                "const all = await api.get('/api/plans');\n"
                "await api.patch(`/api/plans/${planId}`, body);\n"
            ),
        })
        result = scan_wiring("core", repo_root=repo)
        assert result["ok"] is True
        assert result["missing_routes"] == [], result["missing_routes"]
        # Both routes were discovered + both FE calls matched.
        assert result["fe_calls_found"] == 2
        assert result["backend_routes_found"] >= 2

    def test_missing_route_flagged(self, tmp_path: Path):
        repo = _mk_product(tmp_path, "core", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/plans.py": self._ROUTER_PY,
            # FE hits a path with NO backend route (the 404 class).
            "frontend/src/pages/Plans.tsx": (
                "const x = await api.get('/api/subscriptions');\n"
            ),
        })
        result = scan_wiring("core", repo_root=repo)
        assert result["ok"] is True
        assert len(result["missing_routes"]) == 1
        finding = result["missing_routes"][0]
        assert "subscriptions" in finding["detail"]
        assert finding["file"].endswith("Plans.tsx")
        assert finding["line"] == 1

    def test_wrong_method_flagged(self, tmp_path: Path):
        # Route exists for GET but FE does a DELETE — method mismatch is a miss.
        repo = _mk_product(tmp_path, "core", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/plans.py": self._ROUTER_PY,
            "frontend/src/pages/Plans.tsx": "await api.delete('/api/plans');\n",
        })
        result = scan_wiring("core", repo_root=repo)
        assert len(result["missing_routes"]) == 1
        assert "DELETE" in result["missing_routes"][0]["detail"]

    def test_test_file_stub_paths_not_flagged(self, tmp_path: Path):
        # Regression (2026-07-13): a `*.test.ts` api-client test uses stub
        # `/api/x` paths by design — it is NOT a shipped surface, so the
        # route-existence check must skip it (was flagged high, broke CI).
        repo = _mk_product(tmp_path, "core", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/plans.py": self._ROUTER_PY,
            # Real page — matched route, not flagged.
            "frontend/src/pages/Plans.tsx": "await api.get('/api/plans');\n",
            # Test file with a deliberately-fake path — must NOT be flagged.
            "frontend/src/lib/api.test.ts": "await api.get('/api/x');\n",
            # __tests__ dir variant — also skipped.
            "frontend/src/__tests__/client.spec.ts": "await api.post('/api/nope');\n",
        })
        result = scan_wiring("core", repo_root=repo)
        assert result["missing_routes"] == [], result["missing_routes"]


class TestLegADynamicPaths:
    """Finding #6 — scan_wiring's blind spot on dynamically-built FE paths.

    The old `_FE_API_CALL_RE` only captured the FIRST quoted/template-literal
    token immediately after `api.<method>(` — a `+`-concatenation like
    `'/api/n8n/folders/' + id` matched only the literal `'/api/n8n/folders/'`
    piece, silently dropping the ` + id`. That shrinks the segment count (4
    vs. the backend's 5-segment `/api/n8n/folders/{id}`), so `_route_matches`
    (which compares segment-count) reports a FALSE POSITIVE: a route that
    genuinely exists gets flagged `missing_routes` (a 404-class false alarm).
    A fully-dynamic base (`api.post(basePath + '/run')` / `api.get(url)`)
    went the other way — the regex never matched at all, so the call was
    completely invisible (silent-drop, no finding of ANY kind).
    """

    _ROUTER_PY = (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.get('/{id}')\n"
        "def get_folder(id: str):\n    return {}\n"
    )
    _MAIN_PY = (
        "from fastapi import FastAPI\n"
        "from app.routers import n8n\n"
        "app = FastAPI()\n"
        "app.include_router(n8n.router, prefix='/api/n8n/folders')\n"
    )

    def test_string_concat_matching_route_not_flagged(self, tmp_path: Path):
        """THE repro: `'/api/n8n/folders/' + id` DOES match the backend's
        `GET /{id}` (mounted under `/api/n8n/folders`) — must NOT be flagged.
        """
        repo = _mk_product(tmp_path, "social-wiring", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/n8n.py": self._ROUTER_PY,
            "frontend/src/pages/Folders.tsx": (
                "await api.get('/api/n8n/folders/' + id);\n"
            ),
        })
        result = scan_wiring("social-wiring", repo_root=repo)
        assert result["missing_routes"] == [], result["missing_routes"]
        assert result["indeterminate_routes"] == [], result["indeterminate_routes"]
        assert result["fe_calls_found"] == 1

    def test_string_concat_no_matching_route_still_flagged(self, tmp_path: Path):
        # True positive preserved: concatenation to a path with NO backend
        # route is still a genuine 404-class miss.
        repo = _mk_product(tmp_path, "social-wiring", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/n8n.py": self._ROUTER_PY,
            "frontend/src/pages/Folders.tsx": (
                "await api.get('/api/n8n/subscriptions/' + id);\n"
            ),
        })
        result = scan_wiring("social-wiring", repo_root=repo)
        assert len(result["missing_routes"]) == 1
        assert "subscriptions" in result["missing_routes"][0]["detail"]

    def test_mid_segment_concat_fragment_matches_like_template_literal(self, tmp_path: Path):
        # `'/api/n8n/folders/wf-' + id` (no trailing "/" before the var) is a
        # mid-segment fragment merge — normalizes the SAME conservative way a
        # `` `wf-${id}` `` template-literal fragment already does (whole
        # segment treated as dynamic).
        repo = _mk_product(tmp_path, "social-wiring", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/n8n.py": self._ROUTER_PY,
            "frontend/src/pages/Folders.tsx": (
                "await api.get('/api/n8n/folders/wf-' + id);\n"
            ),
        })
        result = scan_wiring("social-wiring", repo_root=repo)
        assert result["missing_routes"] == [], result["missing_routes"]

    def test_fully_dynamic_base_concat_marked_indeterminate(self, tmp_path: Path):
        # `basePath + '/run'` — the FIRST term is itself dynamic, so the
        # segment count is statically unknowable. Must NOT silently vanish
        # (old behaviour: fe_calls_found stayed 0, zero findings of any
        # kind) and must NOT be asserted as "missing" (we can't prove that
        # either) — it comes back as an explicit indeterminate finding.
        repo = _mk_product(tmp_path, "social-wiring", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/n8n.py": self._ROUTER_PY,
            "frontend/src/pages/Folders.tsx": (
                "await api.post(basePath + '/run');\n"
            ),
        })
        result = scan_wiring("social-wiring", repo_root=repo)
        assert result["missing_routes"] == [], result["missing_routes"]
        assert len(result["indeterminate_routes"]) == 1
        finding = result["indeterminate_routes"][0]
        assert finding["line"] == 1
        assert finding["file"].endswith("Folders.tsx")

    def test_bare_variable_arg_marked_indeterminate(self, tmp_path: Path):
        # `api.get(url)` — no quotes at all; the old regex never matched
        # this call (invisible). Now surfaced as indeterminate.
        repo = _mk_product(tmp_path, "social-wiring", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/n8n.py": self._ROUTER_PY,
            "frontend/src/pages/Folders.tsx": "await api.get(url);\n",
        })
        result = scan_wiring("social-wiring", repo_root=repo)
        assert result["missing_routes"] == []
        assert len(result["indeterminate_routes"]) == 1

    def test_template_literal_base_variable_marked_indeterminate(self, tmp_path: Path):
        # `` `${basePath}/run` `` — template literal whose FIRST segment is
        # entirely dynamic; same unknowable-prefix class as concatenation.
        repo = _mk_product(tmp_path, "social-wiring", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/n8n.py": self._ROUTER_PY,
            "frontend/src/pages/Folders.tsx": (
                "await api.get(`${basePath}/run`);\n"
            ),
        })
        result = scan_wiring("social-wiring", repo_root=repo)
        assert result["missing_routes"] == []
        assert len(result["indeterminate_routes"]) == 1


class TestLegAFactoryRouterResolution:
    """Regression (2026-08, discovered on p-studio's `cadastros_router.py`):
    a router built by a FACTORY function — `APIRouter(prefix=f"/api/{param}",
    ...)` where `param` is the factory's own parameter, called with LITERAL
    keyword arguments at module level — was invisible to the regex-only
    extraction (the prefix isn't a quoted literal at the `APIRouter(...)`
    call site), so every route the factory legitimately registers read as
    "does not exist": 8 false-positive `high` findings, red CI.

    Deliberately uses a DIFFERENT factory name / parameter name / resource
    names than p-studio's `montar_router(prefixo=...)` — this pins the
    SHAPE, not a p-studio special-case (the fix must not be a hidden
    slug-branch)."""

    _FACTORY_ROUTER_PY = (
        "from fastapi import APIRouter\n"
        "\n"
        "def build_crud_router(*, resource: str, tag: str):\n"
        '    router = APIRouter(prefix=f"/api/{resource}", tags=[tag])\n'
        "\n"
        '    @router.get("")\n'
        "    def listar():\n        return []\n"
        "\n"
        '    @router.post("")\n'
        "    def criar():\n        return {}\n"
        "\n"
        '    @router.get("/{item_id}")\n'
        "    def obter(item_id: str):\n        return {}\n"
        "\n"
        '    @router.patch("/{item_id}")\n'
        "    def atualizar(item_id: str):\n        return {}\n"
        "\n"
        "    return router\n"
        "\n"
        'widgets_router = build_crud_router(resource="widgets", tag="widgets")\n'
        'gadgets_router = build_crud_router(resource="gadgets", tag="gadgets")\n'
    )
    _MAIN_PY = (
        "from fastapi import FastAPI\n"
        "from app.routers.crud import widgets_router, gadgets_router\n"
        "app = FastAPI()\n"
        "app.include_router(widgets_router)\n"
        "app.include_router(gadgets_router)\n"
    )

    def test_factory_resolved_routes_not_flagged(self, tmp_path: Path):
        """THE repro: FE calls hitting the factory's CONCRETE, literally-
        resolved routes (both call-sites, both CRUD verbs) must NOT be
        flagged — this is the false-positive class itself."""
        repo = _mk_product(tmp_path, "widget-co", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/crud.py": self._FACTORY_ROUTER_PY,
            "frontend/src/pages/Widgets.tsx": (
                "await api.get('/api/widgets');\n"
                "await api.post('/api/widgets', body);\n"
                "await api.patch(`/api/widgets/${id}`, body);\n"
            ),
            "frontend/src/pages/Gadgets.tsx": (
                "await api.get('/api/gadgets');\n"
                "await api.patch(`/api/gadgets/${id}`, body);\n"
            ),
        })
        result = scan_wiring("widget-co", repo_root=repo)
        assert result["missing_routes"] == [], result["missing_routes"]
        assert result["backend_routes_found"] >= 8  # 4 verbs x 2 call-sites

    def test_factory_router_still_flags_genuine_miss(self, tmp_path: Path):
        """🔴 Not a blanket mute: a method the factory never registers
        (DELETE — only get/post/get-by-id/patch are wired) is STILL flagged
        missing, on the SAME factory-produced file/product as the positive
        case above."""
        repo = _mk_product(tmp_path, "widget-co", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/crud.py": self._FACTORY_ROUTER_PY,
            "frontend/src/pages/Widgets.tsx": (
                "await api.delete(`/api/widgets/${id}`);\n"
            ),
        })
        result = scan_wiring("widget-co", repo_root=repo)
        assert len(result["missing_routes"]) == 1
        assert "DELETE" in result["missing_routes"][0]["detail"]

    def test_factory_router_wrong_resource_still_flagged(self, tmp_path: Path):
        """A resource the factory was never CALLED with (no `sprockets_router
        = build_crud_router(resource="sprockets", ...)` call-site exists) is
        still a genuine miss — the factory shape doesn't make every possible
        prefix magically exist."""
        repo = _mk_product(tmp_path, "widget-co", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/crud.py": self._FACTORY_ROUTER_PY,
            "frontend/src/pages/Sprockets.tsx": (
                "await api.get('/api/sprockets');\n"
            ),
        })
        result = scan_wiring("widget-co", repo_root=repo)
        assert len(result["missing_routes"]) == 1
        assert "sprockets" in result["missing_routes"][0]["detail"]

    def test_factory_call_with_non_literal_prefix_arg_falls_back_to_wildcard(self, tmp_path: Path):
        """The call-site binding for the templated parameter is NOT a
        literal (`resource=dynamic_name`) — segment count/shape IS known
        (single dynamic prefix segment) but its literal value is not.
        Per the detector's under-report > over-report charter this must
        still produce a route (as a wildcard `{*}` prefix segment) rather
        than silently vanish — an FE call of the same shape must NOT be
        flagged missing."""
        router_py = self._FACTORY_ROUTER_PY + (
            "dynamic_name = 'whatever'\n"
            "dynamic_router = build_crud_router(resource=dynamic_name, tag='dyn')\n"
        )
        repo = _mk_product(tmp_path, "widget-co", {
            "backend/app/main.py": self._MAIN_PY,
            "backend/app/routers/crud.py": router_py,
            "frontend/src/pages/Anything.tsx": (
                "await api.get('/api/literally-anything');\n"
            ),
        })
        result = scan_wiring("widget-co", repo_root=repo)
        assert result["missing_routes"] == [], result["missing_routes"]


class TestNormalizePath:
    def test_dynamic_segments_normalize_equal(self):
        assert _normalize_path("/api/plans/${planId}") == _normalize_path("/api/plans/{plan_id}")
        assert _normalize_path("/api/plans/:id") == _normalize_path("/api/plans/{id}")

    def test_literal_segments_preserved(self):
        assert _normalize_path("/api/plans/active") != _normalize_path("/api/plans/${id}")

    def test_query_string_stripped(self):
        assert _normalize_path("/api/plans?active=true") == _normalize_path("/api/plans")


# ---------------------------------------------------------------------------
# Leg B — name-on-`nome` column lint
# ---------------------------------------------------------------------------

class TestLegBNomeColumnLint:
    def test_name_on_plans_flagged(self, tmp_path: Path):
        repo = _mk_product(tmp_path, "core", {
            "backend/app/services/subscriptions.py": (
                "rows = sb.table('licenses').select('id, plans(name)').execute()\n"
            ),
        })
        result = scan_wiring("core", repo_root=repo)
        assert len(result["name_on_nome"]) == 1
        f = result["name_on_nome"][0]
        assert "plans" in f["detail"]
        assert "nome" in f["detail"]

    def test_inner_embed_name_flagged(self, tmp_path: Path):
        repo = _mk_product(tmp_path, "core", {
            "backend/app/services/sub.py": (
                "q = sb.table('licenses').select('*, organizations!inner(name)')\n"
            ),
        })
        result = scan_wiring("core", repo_root=repo)
        assert len(result["name_on_nome"]) == 1
        assert "organizations" in result["name_on_nome"][0]["detail"]

    def test_nome_select_not_flagged(self, tmp_path: Path):
        # Correct: reading the real `nome` column.
        repo = _mk_product(tmp_path, "core", {
            "backend/app/services/subscriptions.py": (
                "rows = sb.table('licenses').select('id, plans(nome)').execute()\n"
            ),
        })
        result = scan_wiring("core", repo_root=repo)
        assert result["name_on_nome"] == [], result["name_on_nome"]

    def test_name_on_non_nome_table_not_flagged(self, tmp_path: Path):
        # `users(name)` — users is NOT a nome-table, so don't flag.
        repo = _mk_product(tmp_path, "core", {
            "backend/app/services/svc.py": (
                "rows = sb.table('x').select('users(name)').execute()\n"
            ),
        })
        result = scan_wiring("core", repo_root=repo)
        assert result["name_on_nome"] == []

    def test_first_name_column_not_flagged(self, tmp_path: Path):
        # `plans(first_name)` — word-boundary guard: `first_name` != bare `name`.
        repo = _mk_product(tmp_path, "core", {
            "backend/app/services/svc.py": (
                "rows = sb.table('x').select('plans(first_name)').execute()\n"
            ),
        })
        result = scan_wiring("core", repo_root=repo)
        assert result["name_on_nome"] == []

    def test_nome_table_set_is_configurable_constant(self):
        # The set is an exported module constant for easy extension.
        assert "plans" in _NOME_TABLES
        assert "products" in _NOME_TABLES
        assert "organizations" in _NOME_TABLES


# ---------------------------------------------------------------------------
# Leg C — Promise.all shared-catch
# ---------------------------------------------------------------------------

class TestLegCPromiseAllSharedCatch:
    def test_shared_catch_promise_all_flagged(self, tmp_path: Path):
        repo = _mk_product(tmp_path, "core", {
            "frontend/src/pages/Dashboard.tsx": (
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
            ),
        })
        result = scan_wiring("core", repo_root=repo)
        assert len(result["shared_catch_promise_all"]) == 1
        f = result["shared_catch_promise_all"][0]
        assert "all-zeros" in f["detail"] or "degrade" in f["detail"]

    def test_per_element_catch_not_flagged(self, tmp_path: Path):
        # CORRECT shape (c): EVERY fetch has its own `.catch(() => fallback)`.
        repo = _mk_product(tmp_path, "core", {
            "frontend/src/pages/Dashboard.tsx": (
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
            ),
        })
        result = scan_wiring("core", repo_root=repo)
        assert result["shared_catch_promise_all"] == [], result["shared_catch_promise_all"]

    def test_mixed_one_primary_plus_degrading_aux_not_flagged(self, tmp_path: Path):
        # Leg-4 precision (b): ONE deliberate primary (drives auth/error/logout)
        # + degrading aux already guarded by `.catch()`. Because ≥1 element has
        # a per-element `.catch()`, this is NOT the all-zeros bug → NOT flagged.
        repo = _mk_product(tmp_path, "core", {
            "frontend/src/pages/Dashboard.tsx": (
                "async function load() {\n"
                "  try {\n"
                "    const [me, stats, orgs] = await Promise.all([\n"
                "      api.get('/api/me'),\n"  # primary — its failure SHOULD propagate
                "      api.get('/api/stats').catch(() => ({})),\n"  # aux, degrades
                "      api.get('/api/orgs').catch(() => []),\n"  # aux, degrades
                "    ]);\n"
                "  } catch (e) {\n"
                "    logoutAndRedirect();\n"
                "  }\n"
                "}\n"
            ),
        })
        result = scan_wiring("core", repo_root=repo)
        assert result["shared_catch_promise_all"] == [], result["shared_catch_promise_all"]

    def test_promise_all_no_try_not_flagged(self, tmp_path: Path):
        # No enclosing try/catch → not the shared-catch shape (different smell).
        repo = _mk_product(tmp_path, "core", {
            "frontend/src/pages/Dashboard.tsx": (
                "const [a, b] = await Promise.all([\n"
                "  api.get('/api/stats'),\n"
                "  api.get('/api/orgs'),\n"
                "]);\n"
            ),
        })
        result = scan_wiring("core", repo_root=repo)
        assert result["shared_catch_promise_all"] == []


# ---------------------------------------------------------------------------
# Output shape + next_action
# ---------------------------------------------------------------------------

class TestOutputShape:
    def test_clean_product_next_action_mentions_runtime(self, tmp_path: Path):
        repo = _mk_product(tmp_path, "core", {
            "backend/app/main.py": "app = FastAPI()\n",
            "frontend/src/App.tsx": "export default function App() { return null; }\n",
        })
        result = scan_wiring("core", repo_root=repo)
        assert result["ok"] is True
        assert result["totals"]["total"] == 0
        assert "RUNTIME" in result["next_action"] or "runtime" in result["next_action"]

    def test_totals_aggregate_all_legs(self, tmp_path: Path):
        repo = _mk_product(tmp_path, "core", {
            "backend/app/main.py": "app = FastAPI()\napp.include_router(r, prefix='/api')\n",
            "backend/app/routers/r.py": "@router.get('/ok')\ndef ok(): return []\n",
            "backend/app/services/s.py": "sb.table('x').select('plans(name)')\n",
            "frontend/src/pages/P.tsx": (
                "await api.get('/api/missing');\n"
                "try {\n"
                "  await Promise.all([api.get('/api/a'), api.get('/api/b')]);\n"
                "} catch (e) { setZero(); }\n"
            ),
        })
        result = scan_wiring("core", repo_root=repo)
        t = result["totals"]
        assert t["missing_routes"] >= 1
        assert t["name_on_nome"] == 1
        assert t["shared_catch_promise_all"] == 1
        assert t["total"] == t["missing_routes"] + t["name_on_nome"] + t["shared_catch_promise_all"]
        assert result["next_action"].startswith("Fix:")
