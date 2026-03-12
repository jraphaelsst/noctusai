"""Tests for relatorios (reports) router."""
import pytest


SAMPLE_TRANSACAO_RECEITA = {
    "id": "tx-001",
    "org_id": "test-org-123",
    "valor": 5000.00,
    "tipo": "receita",
    "data": "2026-02-10",
    "categoria": {"id": "cat-001", "nome": "Salario", "icone": "briefcase", "cor": "#22c55e"},
}

SAMPLE_TRANSACAO_DESPESA = {
    "id": "tx-002",
    "org_id": "test-org-123",
    "valor": 1200.00,
    "tipo": "despesa",
    "data": "2026-02-15",
    "categoria": {"id": "cat-002", "nome": "Alimentacao", "icone": "utensils", "cor": "#ef4444"},
}


class TestRelatorioMensal:
    def test_returns_monthly_report(self, client):
        client._mock_supabase.set_table_data("transacoes", [SAMPLE_TRANSACAO_RECEITA, SAMPLE_TRANSACAO_DESPESA])
        client._mock_supabase.set_table_data("resumos_mensais", [])
        response = client.get("/api/relatorios/mensal?mes=2026-02")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        result = data["data"]
        assert "mes" in result
        assert "receita_total" in result
        assert "despesa_total" in result
        assert "fluxo_liquido" in result

    def test_requires_mes_param(self, client):
        response = client.get("/api/relatorios/mensal")
        assert response.status_code == 422

    def test_validates_mes_format(self, client):
        response = client.get("/api/relatorios/mensal?mes=2026-2")
        assert response.status_code == 422

    def test_validates_mes_format_invalid(self, client):
        response = client.get("/api/relatorios/mensal?mes=abc")
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.get("/api/relatorios/mensal?mes=2026-02")
        assert response.status_code == 401


class TestRelatorioAnual:
    def test_returns_annual_report(self, client):
        client._mock_supabase.set_table_data("transacoes", [SAMPLE_TRANSACAO_RECEITA, SAMPLE_TRANSACAO_DESPESA])
        client._mock_supabase.set_table_data("resumos_mensais", [])
        response = client.get("/api/relatorios/anual?ano=2026")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        result = data["data"]
        assert "ano" in result
        assert "receita_anual" in result
        assert "meses" in result
        assert len(result["meses"]) == 12

    def test_requires_ano_param(self, client):
        response = client.get("/api/relatorios/anual")
        assert response.status_code == 422

    def test_validates_ano_format(self, client):
        response = client.get("/api/relatorios/anual?ano=26")
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.get("/api/relatorios/anual?ano=2026")
        assert response.status_code == 401


class TestFluxoCaixa:
    def test_returns_cash_flow(self, client):
        client._mock_supabase.set_table_data("transacoes", [SAMPLE_TRANSACAO_RECEITA, SAMPLE_TRANSACAO_DESPESA])
        response = client.get("/api/relatorios/fluxo-caixa?data_inicio=2026-02-01&data_fim=2026-02-28")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        result = data["data"]
        assert "fluxo" in result

    def test_requires_both_dates(self, client):
        response = client.get("/api/relatorios/fluxo-caixa?data_inicio=2026-02-01")
        assert response.status_code == 422

    def test_validates_date_format(self, client):
        response = client.get("/api/relatorios/fluxo-caixa?data_inicio=2026-02&data_fim=2026-02-28")
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.get("/api/relatorios/fluxo-caixa?data_inicio=2026-02-01&data_fim=2026-02-28")
        assert response.status_code == 401
