"""
Tests for BI Dashboard endpoint — /api/bi/dashboard
Covers the comprehensive dashboard summary aggregation.
"""
import pytest


class TestDashboardResumo:
    def test_dashboard_empty(self, client):
        for table in ("clientes", "ativos", "propostas", "lancamentos",
                       "contratos", "eventos", "negociacoes"):
            client._mock_supabase.set_table_data(table, [])
        resp = client.get("/api/bi/dashboard")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "kpis" in data
        assert "funil" in data
        assert "financeiro" in data

    def test_dashboard_with_data(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "etapa_atual": "prospeccao", "created_at": "2026-02-01T10:00:00", "valor_estimado": 100000},
            {"id": "c2", "etapa_atual": "qualificacao", "created_at": "2026-02-15T10:00:00", "valor_estimado": 200000},
        ])
        client._mock_supabase.set_table_data("ativos", [
            {"id": "a1", "natureza": "imovel", "status": "ativo", "valor": 500000},
        ])
        client._mock_supabase.set_table_data("propostas", [
            {"id": "p1", "status": "aceita", "valor_proposta": 450000, "created_at": "2026-02-10"},
        ])
        client._mock_supabase.set_table_data("lancamentos", [
            {"id": "l1", "tipo": "receita", "status": "pago", "valor": 5000, "data_vencimento": "2026-02-15"},
        ])
        client._mock_supabase.set_table_data("contratos", [
            {"id": "ct1", "status": "ativo", "valor_total": 500000},
        ])
        client._mock_supabase.set_table_data("eventos", [])
        client._mock_supabase.set_table_data("negociacoes", [
            {"id": "n1", "status_etapa": "negociacao"},
        ])

        resp = client.get("/api/bi/dashboard")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["kpis"]["total_clientes"] == 2
        assert data["kpis"]["imoveis_ativos"] == 1
        assert data["kpis"]["propostas_aceitas"] == 1
        assert data["kpis"]["contratos_ativos"] == 1
        assert data["kpis"]["negociacoes_abertas"] == 1
