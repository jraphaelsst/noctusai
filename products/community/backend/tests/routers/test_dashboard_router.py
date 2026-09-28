"""Tests for `dashboard_router` — CONTRACT.md §Cashflow + dashboard,
slice BE-C (HTTP wiring only — the KPI/series math itself is covered by
`tests/services/test_dashboard_service.py`, one test per definition).
"""
from datetime import datetime, timezone

from noctusai_lib.primitives.timeutil import frozen_time

from tests.conftest import ORG_UUID, seed_community_role

_NOW = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


class TestDashboardAuthBoundary:
    def test_without_auth_401(self, client):
        assert client.raw().get("/api/dashboard").status_code == 401


class TestDashboardRoleGate:
    def test_moderador_can_read(self, client):
        seed_community_role(client, org_role="moderador")
        with frozen_time(_NOW):
            assert client.get("/api/dashboard").status_code == 200

    def test_admin_can_read(self, client):
        seed_community_role(client, org_role="admin")
        with frozen_time(_NOW):
            assert client.get("/api/dashboard").status_code == 200


class TestDashboardShape:
    def test_empty_org_returns_zeroed_shape_never_an_error(self, client):
        with frozen_time(_NOW):
            resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert body["kpis"]["membros_total"] == 0
        assert body["kpis"]["mrr_centavos"] == 0
        assert body["kpis"]["arpu_centavos"] == 0
        assert body["kpis"]["churn_mes_pct"] == 0.0
        assert body["kpis"]["conversao_pago_pct"] == 0.0
        # default meses=12 — the window is still zero-filled, never empty.
        assert len(body["series"]["mensal"]) == 12
        assert all(m["mrr_centavos"] == 0 for m in body["series"]["mensal"])
        assert "gerado_em" in body

    def test_meses_query_bounds_the_series_length(self, client):
        with frozen_time(_NOW):
            resp = client.get("/api/dashboard", params={"meses": 3})
        assert resp.status_code == 200
        mensal = resp.json()["series"]["mensal"]
        assert len(mensal) == 3
        assert [m["mes"] for m in mensal] == ["2026-04", "2026-05", "2026-06"]

    def test_meses_out_of_range_422(self, client):
        resp = client.get("/api/dashboard", params={"meses": 25})
        assert resp.status_code == 422

    def test_por_plano_lists_every_org_plano(self, client):
        client.mock_supabase.set_table_data("planos", [{
            "id": "11111111-1111-1111-1111-111111111111", "org_id": ORG_UUID,
            "nome": "Ouvinte", "descricao": None, "preco_centavos": 700, "ciclo": "mensal",
            "entitlements": {"grupoterapia": "ouvir"}, "ativo": True, "ordem": 1,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }])
        with frozen_time(_NOW):
            resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        por_plano = resp.json()["kpis"]["por_plano"]
        assert len(por_plano) == 1
        assert por_plano[0]["nome"] == "Ouvinte"
        assert por_plano[0]["nivel_grupoterapia"] == "ouvir"
        assert por_plano[0]["membros"] == 0
