"""Tests for patrimonio (net worth) router."""
import pytest


SAMPLE_CONTA = {
    "id": "conta-001",
    "nome": "Conta Corrente",
    "tipo": "corrente",
    "saldo": 15000.00,
    "ativo": True,
}

SAMPLE_ATIVO = {
    "id": "ativo-001",
    "ticker": "PETR4",
    "valor_atual": 5000.00,
    "carteira_id": "cart-001",
}

SAMPLE_SNAPSHOT = {
    "id": "snap-001",
    "org_id": "test-org-123",
    "data": "2026-02-01",
    "total_ativos": 20000.00,
    "total_passivos": 0,
    "patrimonio_liquido": 20000.00,
    "detalhamento": {"contas": [], "investimentos": []},
}


class TestPatrimonioAtual:
    def test_returns_current_net_worth(self, client):
        client._mock_supabase.set_table_data("contas", [SAMPLE_CONTA])
        client._mock_supabase.set_table_data("ativos", [SAMPLE_ATIVO])
        response = client.get("/api/patrimonio/atual")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        result = data["data"]
        assert "total_ativos" in result
        assert "total_passivos" in result
        assert "patrimonio_liquido" in result
        assert "detalhamento" in result

    def test_empty_accounts(self, client):
        client._mock_supabase.set_table_data("contas", [])
        client._mock_supabase.set_table_data("ativos", [])
        response = client.get("/api/patrimonio/atual")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total_ativos"] == 0
        assert data["total_passivos"] == 0
        assert data["patrimonio_liquido"] == 0

    def test_requires_auth(self, client):
        response = client._tc.get("/api/patrimonio/atual")
        assert response.status_code == 401


class TestPatrimonioHistorico:
    def test_returns_history(self, client):
        client._mock_supabase.set_table_data("patrimonio_snapshots", [SAMPLE_SNAPSHOT])
        response = client.get("/api/patrimonio/historico")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total" in data

    def test_custom_limite(self, client):
        client._mock_supabase.set_table_data("patrimonio_snapshots", [SAMPLE_SNAPSHOT])
        response = client.get("/api/patrimonio/historico?limite=12")
        assert response.status_code == 200

    def test_limite_validation_min(self, client):
        response = client.get("/api/patrimonio/historico?limite=0")
        assert response.status_code == 422

    def test_limite_validation_max(self, client):
        response = client.get("/api/patrimonio/historico?limite=121")
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.get("/api/patrimonio/historico")
        assert response.status_code == 401


class TestCriarSnapshot:
    def test_creates_snapshot(self, client):
        client._mock_supabase.set_table_data("contas", [SAMPLE_CONTA])
        client._mock_supabase.set_table_data("ativos", [SAMPLE_ATIVO])
        client._mock_supabase.set_table_data("patrimonio_snapshots", [SAMPLE_SNAPSHOT])
        response = client.post("/api/patrimonio/snapshot")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_creates_snapshot_with_date(self, client):
        client._mock_supabase.set_table_data("contas", [SAMPLE_CONTA])
        client._mock_supabase.set_table_data("ativos", [])
        client._mock_supabase.set_table_data("patrimonio_snapshots", [SAMPLE_SNAPSHOT])
        response = client.post("/api/patrimonio/snapshot?data_snapshot=2026-02-15")
        assert response.status_code == 200

    def test_requires_auth(self, client):
        response = client._tc.post("/api/patrimonio/snapshot")
        assert response.status_code == 401
