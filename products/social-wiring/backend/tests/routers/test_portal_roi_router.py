"""`/api/portal-roi` — auth boundary, CRUD round-trips, and the null-vs-zero
regression this whole project exists to fix.

**Strict `== 401`, never `in (401, 404)`.** A permissive tuple is a
false-green — it passes when the route doesn't exist at all, and it passes
when validation runs before auth. Only the exact code proves the guard
fired. → `KB § PATTERNS/compliance/auth-boundary-false-green.md`

**`test_unrecorded_investimento_is_null_not_zero_regression`** is the pin.
It builds EXACTLY the pre-047 failure scenario — a portal with real leads
and zero `lead_campanhas` rows — and asserts `investimento`/`cpl` come back
`null`. Against the view as `043` originally shipped it (`COALESCE(c.
investimento, 0) / NULLIF(...)`), this test FAILS: `cpl` reads `0.00`, the
exact "spend more here, it's free" lie `portal-roi-PROJECT.md` §2 exists to
kill. Rows are seeded directly against the schema-scoped mock (there is no
`/leads` or `/vendas` write surface in THIS product's routers under test)
so each scenario is exact and independent of any other module's fixtures.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import coerce_org_uuid
from app.services.portal_roi_service import get_portal_roi_client
from tests.conftest import (  # type: ignore[attr-defined]
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)

ORG_RAW = "test-org-123"
ORG_ID = str(coerce_org_uuid(ORG_RAW))


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _seed_source(scoped, *, source_id=None, slug="zap", label="ZAP", categoria="portal") -> str:
    source_id = source_id or str(uuid4())
    scoped.table("lead_sources").insert(
        {
            "id": source_id,
            "org_id": ORG_ID,
            "slug": slug,
            "label": label,
            "categoria": categoria,
            "cor": None,
            "ativo": True,
            "ordem": 0,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": None,
        }
    ).execute()
    return source_id


def _seed_lead(scoped, *, origem_id: str, data_entrada: str = "2026-07-15") -> None:
    scoped.table("leads").insert(
        {
            "id": str(uuid4()),
            "org_id": ORG_ID,
            "data_entrada": data_entrada,
            "origem_id": origem_id,
            "tipo_lead": "desconhecido",
            "needs_review": False,
            "created_at": f"{data_entrada}T00:00:00+00:00",
        }
    ).execute()


def _seed_venda(scoped, *, origem_id: str, valor: float, data_venda: str = "2026-07-20") -> None:
    scoped.table("lead_vendas").insert(
        {
            "id": str(uuid4()),
            "org_id": ORG_ID,
            "origem_id": origem_id,
            "data_venda": data_venda,
            "valor": valor,
            "created_at": f"{data_venda}T00:00:00+00:00",
        }
    ).execute()


def _seed_campanha(
    scoped,
    *,
    origem_id: str,
    investimento: float,
    periodo_inicio: str = "2026-07-01",
    periodo_fim: str = "2026-07-31",
) -> str:
    row_id = str(uuid4())
    scoped.table("lead_campanhas").insert(
        {
            "id": row_id,
            "org_id": ORG_ID,
            "origem_id": origem_id,
            "periodo_inicio": periodo_inicio,
            "periodo_fim": periodo_fim,
            "investimento": investimento,
            "impressoes": None,
            "cliques": None,
            "leads": None,
            "visitas_perfil": None,
            "engajamento": None,
            "observacoes": None,
            "created_at": "2026-08-01T00:00:00+00:00",
            "updated_at": None,
        }
    ).execute()
    return row_id


@pytest.fixture
def anon_client():
    """A TestClient that sends NO Authorization header — see
    `imoveis_router` test's identical fixture for why the shared `client`
    fixture can never produce a 401."""
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=ORG_RAW))
    )
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        tc = TestClient(app)
        yield tc
        app.dependency_overrides.clear()


@pytest.fixture
def scoped(client):
    """The `social_wiring`-scoped mock the router's own DI seam
    (`get_portal_roi_client`) resolves and caches — seeding rows through
    THIS SAME instance is what makes them visible to a subsequent
    request in the same test (see `portal_roi_service.py`'s module
    docstring: a *fresh* `.schema()` call would silently lose them)."""
    return get_portal_roi_client()


# ─── Auth boundary — strict 401 ────────────────────────────────────────

UNAUTHENTICATED_ROUTES = [
    ("get", "/api/portal-roi/resumo"),
    ("get", "/api/portal-roi/campanhas"),
    ("post", "/api/portal-roi/campanhas"),
    ("patch", f"/api/portal-roi/campanhas/{uuid4()}"),
    ("delete", f"/api/portal-roi/campanhas/{uuid4()}"),
    ("get", "/api/portal-roi/origens"),
]


@pytest.mark.parametrize("method,path", UNAUTHENTICATED_ROUTES)
def test_unauthenticated_requests_are_strictly_401(anon_client, method, path):
    resp = getattr(anon_client, method)(path)
    assert resp.status_code == 401, f"{method.upper()} {path} -> {resp.status_code}: {resp.text}"


def test_every_portal_roi_route_requires_auth(anon_client):
    """Enumerates mounted routes rather than a hand list — guards against
    a future route landing without `Depends(get_current_user_org)`."""
    from app.main import app

    paths = {
        (method.lower(), route.path)
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/portal-roi")
        for method in getattr(route, "methods", set())
        if method.lower() in {"get", "post", "patch", "delete"}
    }
    assert paths, "no /api/portal-roi routes are mounted — the router isn't wired"

    for method, path in sorted(paths):
        concrete = path.replace("{campanha_id}", str(uuid4()))
        resp = getattr(anon_client, method)(concrete)
        assert resp.status_code == 401, (
            f"{method.upper()} {concrete} -> {resp.status_code} "
            "(every /api/portal-roi route must require auth)"
        )


def test_router_is_mounted(anon_client):
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/portal-roi/resumo" in paths
    assert "/api/portal-roi/campanhas" in paths
    assert "/api/portal-roi/origens" in paths


# ─── origens ────────────────────────────────────────────────────────────


def test_origens_lists_sources(client, scoped):
    _seed_source(scoped, slug="zap", label="ZAP")
    _seed_source(scoped, slug="senseys", label="Senseys")
    resp = client.get("/api/portal-roi/origens", headers=_auth())
    assert resp.status_code == 200, resp.text
    origens = resp.json()["origens"]
    assert {o["slug"] for o in origens} == {"zap", "senseys"}


def test_origens_empty(client):
    resp = client.get("/api/portal-roi/origens", headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["origens"] == []


# ─── campanhas CRUD ─────────────────────────────────────────────────────


def test_create_campanha_201(client, scoped):
    origem_id = _seed_source(scoped)
    resp = client.post(
        "/api/portal-roi/campanhas",
        json={
            "origem_id": origem_id,
            "periodo_inicio": "2026-07-01",
            "periodo_fim": "2026-07-31",
            "investimento": 3200.00,
            "cliques": 4300,
            "leads": 812,
        },
        headers=_auth(),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["investimento"] == 3200.00
    assert body["origem_id"] == origem_id
    assert body["origem_label"] == "ZAP"
    # GENERATED, computed server-side — investimento / leads.
    assert body["cpl"] == pytest.approx(3200.00 / 812)


def test_create_campanha_unknown_origem_404(client, scoped):
    resp = client.post(
        "/api/portal-roi/campanhas",
        json={
            "origem_id": str(uuid4()),
            "periodo_inicio": "2026-07-01",
            "periodo_fim": "2026-07-31",
            "investimento": 100,
        },
        headers=_auth(),
    )
    assert resp.status_code == 404, resp.text


def test_create_campanha_periodo_fim_before_inicio_422(client, scoped):
    origem_id = _seed_source(scoped)
    resp = client.post(
        "/api/portal-roi/campanhas",
        json={
            "origem_id": origem_id,
            "periodo_inicio": "2026-07-31",
            "periodo_fim": "2026-07-01",
            "investimento": 100,
        },
        headers=_auth(),
    )
    assert resp.status_code == 422, resp.text


def test_create_campanha_negative_investimento_422(client, scoped):
    origem_id = _seed_source(scoped)
    resp = client.post(
        "/api/portal-roi/campanhas",
        json={
            "origem_id": origem_id,
            "periodo_inicio": "2026-07-01",
            "periodo_fim": "2026-07-31",
            "investimento": -1,
        },
        headers=_auth(),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("field", ["cpc", "cpl", "custo_visita"])
def test_create_campanha_rejects_generated_columns_422(client, scoped, field):
    """`extra='forbid'` — never silently drop a write naming a GENERATED
    column, per contract §3.3."""
    origem_id = _seed_source(scoped)
    resp = client.post(
        "/api/portal-roi/campanhas",
        json={
            "origem_id": origem_id,
            "periodo_inicio": "2026-07-01",
            "periodo_fim": "2026-07-31",
            "investimento": 100,
            field: 1.23,
        },
        headers=_auth(),
    )
    assert resp.status_code == 422, resp.text


def test_duplicate_period_409_returns_conflicting_id(client, scoped):
    """The UNIQUE (org_id, origem_id, periodo_inicio, periodo_fim) is
    deliberate — re-importing a month must UPDATE, not duplicate. The 409
    MUST carry the existing row's id so the FE can offer that update."""
    origem_id = _seed_source(scoped)
    body = {
        "origem_id": origem_id,
        "periodo_inicio": "2026-07-01",
        "periodo_fim": "2026-07-31",
        "investimento": 100,
    }
    first = client.post("/api/portal-roi/campanhas", json=body, headers=_auth())
    assert first.status_code == 201, first.text
    existing_id = first.json()["id"]

    second = client.post("/api/portal-roi/campanhas", json=body, headers=_auth())
    assert second.status_code == 409, second.text
    detail = second.json()
    # AppException handler shape: {"error": {"code", "message", "details"}}.
    assert detail["error"]["details"]["id"] == existing_id


def test_list_campanhas_after_create(client, scoped):
    origem_id = _seed_source(scoped, label="ZAP")
    client.post(
        "/api/portal-roi/campanhas",
        json={
            "origem_id": origem_id,
            "periodo_inicio": "2026-07-01",
            "periodo_fim": "2026-07-31",
            "investimento": 500,
        },
        headers=_auth(),
    )
    resp = client.get("/api/portal-roi/campanhas", headers=_auth())
    assert resp.status_code == 200, resp.text
    campanhas = resp.json()["campanhas"]
    assert len(campanhas) == 1
    assert campanhas[0]["origem_label"] == "ZAP"
    assert campanhas[0]["investimento"] == 500


def test_update_campanha(client, scoped):
    origem_id = _seed_source(scoped)
    created = client.post(
        "/api/portal-roi/campanhas",
        json={
            "origem_id": origem_id,
            "periodo_inicio": "2026-07-01",
            "periodo_fim": "2026-07-31",
            "investimento": 100,
        },
        headers=_auth(),
    ).json()
    resp = client.patch(
        f"/api/portal-roi/campanhas/{created['id']}",
        json={"investimento": 250.5},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["investimento"] == 250.5


def test_update_campanha_nonexistent_404(client):
    resp = client.patch(
        f"/api/portal-roi/campanhas/{uuid4()}",
        json={"investimento": 1},
        headers=_auth(),
    )
    assert resp.status_code == 404


def test_update_campanha_negative_investimento_422(client, scoped):
    origem_id = _seed_source(scoped)
    created = client.post(
        "/api/portal-roi/campanhas",
        json={
            "origem_id": origem_id,
            "periodo_inicio": "2026-07-01",
            "periodo_fim": "2026-07-31",
            "investimento": 100,
        },
        headers=_auth(),
    ).json()
    resp = client.patch(
        f"/api/portal-roi/campanhas/{created['id']}",
        json={"investimento": -5},
        headers=_auth(),
    )
    assert resp.status_code == 422, resp.text


def test_delete_campanha(client, scoped):
    origem_id = _seed_source(scoped)
    created = client.post(
        "/api/portal-roi/campanhas",
        json={
            "origem_id": origem_id,
            "periodo_inicio": "2026-07-01",
            "periodo_fim": "2026-07-31",
            "investimento": 100,
        },
        headers=_auth(),
    ).json()
    resp = client.delete(f"/api/portal-roi/campanhas/{created['id']}", headers=_auth())
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": True, "id": created["id"]}

    resp2 = client.get("/api/portal-roi/campanhas", headers=_auth())
    assert resp2.json()["campanhas"] == []


def test_delete_campanha_nonexistent_404(client):
    resp = client.delete(f"/api/portal-roi/campanhas/{uuid4()}", headers=_auth())
    assert resp.status_code == 404


# ─── resumo — the null-vs-zero regression pin ──────────────────────────


def test_unrecorded_investimento_is_null_not_zero_regression(client, scoped):
    """THE pin. A portal with real leads and ZERO `lead_campanhas` rows
    must report `investimento: null` and `cpl: null` — never `0.00`.

    Against the pre-047 view (`COALESCE(c.investimento, 0) / NULLIF(...)`)
    this fails: cpl comes back `0.00`, the exact "spend more here, it's
    free" lie `portal-roi-PROJECT.md` §2 exists to kill."""
    origem_id = _seed_source(scoped, slug="senseys", label="Senseys")
    for _ in range(5):
        _seed_lead(scoped, origem_id=origem_id)
    # Deliberately NO lead_campanhas row for this origem.

    resp = client.get("/api/portal-roi/resumo", headers=_auth())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    portal = next(p for p in body["portais"] if p["origem_id"] == origem_id)
    assert portal["total_leads"] == 5
    assert portal["investimento"] is None
    assert portal["cpl"] is None
    assert portal["roi"] is None
    # Platform totals: nothing recorded anywhere -> unrecorded, not 0.
    assert body["totais"]["investimento"] is None
    assert body["totais"]["cpl"] is None


def test_recorded_zero_investimento_is_a_real_zero_not_null(client, scoped):
    """The other half of the same fact: an EXPLICIT `investimento=0` row
    (the operator deliberately entered "R$ 0,00") must survive as a real
    `0.00`, distinct from the unrecorded case above."""
    origem_id = _seed_source(scoped, slug="indicacao", label="Indicação")
    for _ in range(3):
        _seed_lead(scoped, origem_id=origem_id)
    _seed_campanha(scoped, origem_id=origem_id, investimento=0)

    resp = client.get("/api/portal-roi/resumo", headers=_auth())
    body = resp.json()
    portal = next(p for p in body["portais"] if p["origem_id"] == origem_id)
    assert portal["investimento"] == 0
    assert portal["cpl"] == 0
    # roi stays null even for a recorded zero — dividing by zero spend is
    # undefined regardless of WHY investimento is zero (047's verdict).
    assert portal["roi"] is None


def test_investimento_with_leads_and_spend_computes_cpl(client, scoped):
    origem_id = _seed_source(scoped, slug="zap", label="ZAP")
    for _ in range(4):
        _seed_lead(scoped, origem_id=origem_id)
    _seed_campanha(scoped, origem_id=origem_id, investimento=400)

    resp = client.get("/api/portal-roi/resumo", headers=_auth())
    portal = next(p for p in resp.json()["portais"] if p["origem_id"] == origem_id)
    assert portal["investimento"] == 400
    assert portal["cpl"] == 100.0  # 400 / 4


def test_taxa_conversao_is_a_genuine_zero_when_vendas_tracked_and_none_closed(client, scoped):
    """Verdict recorded in `047`'s header: a genuine 0% (some leads, zero
    matching lead_vendas rows) reports `0`, not `null` — `lead_vendas` has
    no coverage marker to distinguish "closed nothing" from "not tracked",
    and total_vendas/valor_vendas are already decided to stay COALESCE-0
    (`043`'s header) — taxa_conversao inherits that."""
    origem_id = _seed_source(scoped, slug="meta-ads", label="Meta Ads")
    for _ in range(10):
        _seed_lead(scoped, origem_id=origem_id)
    # No lead_vendas rows for this origem.

    resp = client.get("/api/portal-roi/resumo", headers=_auth())
    portal = next(p for p in resp.json()["portais"] if p["origem_id"] == origem_id)
    assert portal["total_vendas"] == 0
    assert portal["taxa_conversao"] == 0


def test_taxa_conversao_null_when_no_leads(client, scoped):
    origem_id = _seed_source(scoped, slug="empty", label="Empty Portal")
    resp = client.get("/api/portal-roi/resumo", headers=_auth())
    portal = next(p for p in resp.json()["portais"] if p["origem_id"] == origem_id)
    assert portal["total_leads"] == 0
    assert portal["taxa_conversao"] is None


def test_taxa_conversao_reflects_closed_deals(client, scoped):
    origem_id = _seed_source(scoped, slug="tempo-real", label="Tempo Real")
    for _ in range(4):
        _seed_lead(scoped, origem_id=origem_id)
    _seed_venda(scoped, origem_id=origem_id, valor=500_000)

    resp = client.get("/api/portal-roi/resumo", headers=_auth())
    body = resp.json()
    portal = next(p for p in body["portais"] if p["origem_id"] == origem_id)
    assert portal["total_vendas"] == 1
    assert portal["valor_vendas"] == 500_000
    assert portal["taxa_conversao"] == pytest.approx(0.25)  # 1 / 4


def test_resumo_period_filter_excludes_out_of_range_campanha(client, scoped):
    origem_id = _seed_source(scoped, slug="zap2", label="ZAP")
    _seed_lead(scoped, origem_id=origem_id, data_entrada="2026-06-15")
    _seed_campanha(
        scoped,
        origem_id=origem_id,
        investimento=1000,
        periodo_inicio="2026-06-01",
        periodo_fim="2026-06-30",
    )

    # July window — the June spend + June lead fall outside it.
    resp = client.get(
        "/api/portal-roi/resumo",
        params={"periodo_inicio": "2026-07-01", "periodo_fim": "2026-07-31"},
        headers=_auth(),
    )
    body = resp.json()
    assert body["periodo"] == {"inicio": "2026-07-01", "fim": "2026-07-31"}
    portal = next(p for p in body["portais"] if p["origem_id"] == origem_id)
    assert portal["investimento"] is None
    assert portal["total_leads"] == 0

    # All-time — both are visible.
    resp_all = client.get("/api/portal-roi/resumo", headers=_auth())
    assert resp_all.json()["periodo"] is None
    portal_all = next(p for p in resp_all.json()["portais"] if p["origem_id"] == origem_id)
    assert portal_all["investimento"] == 1000
    assert portal_all["total_leads"] == 1
