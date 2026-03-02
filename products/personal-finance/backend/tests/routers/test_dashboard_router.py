"""Tests for dashboard (KPIs and summary) router."""
import pytest


SAMPLE_CONTA = {
    "id": "conta-001",
    "nome": "Corrente",
    "tipo": "corrente",
    "saldo": 5000.00,
    "ativo": True,
}

SAMPLE_ATIVO = {
    "id": "ativo-001",
    "org_id": "test-org-123",
    "ticker": "PETR4",
    "valor_atual": 3800.00,
    "ganho_perda": 250.00,
    "carteira_id": "cart-001",
}

SAMPLE_TRANSACAO = {
    "id": "trans-001",
    "org_id": "test-org-123",
    "conta_id": "conta-001",
    "data": "2026-02-15",
    "valor": 150.00,
    "tipo": "despesa",
    "descricao": "Supermercado",
    "conta": {"id": "conta-001", "nome": "Corrente", "cor": "#6366f1"},
    "categoria": {"id": "cat-001", "nome": "Alimentacao", "icone": "utensils", "cor": "#ef4444"},
}

SAMPLE_RECORRENTE = {
    "id": "rec-001",
    "org_id": "test-org-123",
    "descricao": "Netflix",
    "valor": 39.90,
    "ativo": True,
    "proxima_data": "2026-03-01",
    "categoria": {"id": "cat-002", "nome": "Lazer", "icone": "tv", "cor": "#8b5cf6"},
}

SAMPLE_META = {
    "id": "meta-001",
    "org_id": "test-org-123",
    "nome": "Fundo de Emergencia",
    "valor_alvo": 30000.00,
    "valor_atual": 15000.00,
    "status": "ativa",
    "prioridade": "alta",
}


class TestDashboardKpis:
    def test_returns_kpi_data(self, client):
        # Set up mock data for patrimonio service
        client._mock_supabase.set_table_data("contas", [SAMPLE_CONTA])
        client._mock_supabase.set_table_data("ativos", [SAMPLE_ATIVO])
        # Set up mock data for relatorios service (monthly transactions)
        client._mock_supabase.set_table_data("transacoes", [
            {"tipo": "receita", "valor": 8000.00, "data": "2026-02-05", "categoria": None},
            {"tipo": "despesa", "valor": 3000.00, "data": "2026-02-10", "categoria": None},
        ])

        response = client.get("/api/dashboard/kpis")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_kpis_contain_expected_fields(self, client):
        client._mock_supabase.set_table_data("contas", [SAMPLE_CONTA])
        client._mock_supabase.set_table_data("ativos", [SAMPLE_ATIVO])
        client._mock_supabase.set_table_data("transacoes", [])

        response = client.get("/api/dashboard/kpis")
        assert response.status_code == 200
        kpis = response.json()["data"]
        assert "patrimonio_liquido" in kpis
        assert "total_ativos" in kpis
        assert "total_passivos" in kpis
        assert "receita_mensal" in kpis
        assert "despesa_mensal" in kpis
        assert "fluxo_caixa_mensal" in kpis
        assert "taxa_poupanca" in kpis
        assert "retorno_investimentos" in kpis
        assert "valor_investimentos" in kpis

    def test_requires_auth(self, client):
        response = client._tc.get("/api/dashboard/kpis")
        assert response.status_code == 401


class TestDashboardResumo:
    def test_returns_summary_data(self, client):
        client._mock_supabase.set_table_data("transacoes", [SAMPLE_TRANSACAO])
        client._mock_supabase.set_table_data("recorrentes", [SAMPLE_RECORRENTE])
        client._mock_supabase.set_table_data("metas", [SAMPLE_META])

        response = client.get("/api/dashboard/resumo")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_resumo_contains_expected_sections(self, client):
        client._mock_supabase.set_table_data("transacoes", [])
        client._mock_supabase.set_table_data("recorrentes", [])
        client._mock_supabase.set_table_data("metas", [])

        response = client.get("/api/dashboard/resumo")
        assert response.status_code == 200
        resumo = response.json()["data"]
        assert "transacoes_recentes" in resumo
        assert "proximas_contas" in resumo
        assert "metas_ativas" in resumo

    def test_transacoes_recentes_is_list(self, client):
        client._mock_supabase.set_table_data("transacoes", [SAMPLE_TRANSACAO])
        client._mock_supabase.set_table_data("recorrentes", [])
        client._mock_supabase.set_table_data("metas", [])

        response = client.get("/api/dashboard/resumo")
        assert response.status_code == 200
        resumo = response.json()["data"]
        assert isinstance(resumo["transacoes_recentes"], list)

    def test_metas_ativas_has_percentual(self, client):
        client._mock_supabase.set_table_data("transacoes", [])
        client._mock_supabase.set_table_data("recorrentes", [])
        client._mock_supabase.set_table_data("metas", [SAMPLE_META])

        response = client.get("/api/dashboard/resumo")
        assert response.status_code == 200
        resumo = response.json()["data"]
        metas = resumo["metas_ativas"]
        if metas:
            assert "percentual" in metas[0]

    def test_requires_auth(self, client):
        response = client._tc.get("/api/dashboard/resumo")
        assert response.status_code == 401


class TestHealth:
    def test_health_check(self, client):
        response = client._tc.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["product"] == "personal-finance"
        assert "version" in data
