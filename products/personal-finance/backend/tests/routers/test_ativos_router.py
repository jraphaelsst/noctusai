"""Tests for ativos (investment holdings) router."""
import pytest


SAMPLE_ATIVO = {
    "id": "ativo-001",
    "carteira_id": "cart-001",
    "org_id": "test-org-123",
    "ticker": "PETR4",
    "nome": "Petrobras PN",
    "tipo": "acao",
    "quantidade": 100,
    "preco_medio": 35.50,
    "preco_atual": 38.00,
    "valor_atual": 3800.00,
    "ganho_perda": 250.00,
    "ganho_perda_pct": 7.04,
    "setor": "Energia",
    "created_at": "2026-01-10T10:00:00",
}

SAMPLE_ATIVO_2 = {
    "id": "ativo-002",
    "carteira_id": "cart-001",
    "org_id": "test-org-123",
    "ticker": "VALE3",
    "nome": "Vale ON",
    "tipo": "acao",
    "quantidade": 50,
    "preco_medio": 68.00,
    "preco_atual": 72.50,
    "valor_atual": 3625.00,
    "ganho_perda": 225.00,
    "ganho_perda_pct": 6.62,
    "setor": "Mineracao",
    "created_at": "2026-01-15T10:00:00",
}

SAMPLE_FII = {
    "id": "ativo-003",
    "carteira_id": "cart-001",
    "org_id": "test-org-123",
    "ticker": "HGLG11",
    "nome": "CSHG Logistica",
    "tipo": "fii",
    "quantidade": 20,
    "preco_medio": 155.00,
    "preco_atual": 160.00,
    "valor_atual": 3200.00,
    "ganho_perda": 100.00,
    "ganho_perda_pct": 3.23,
    "setor": "Logistica",
    "created_at": "2026-01-20T10:00:00",
}


class TestListarAtivos:
    def test_returns_holdings_list(self, client):
        client._mock_supabase.set_table_data("ativos", [SAMPLE_ATIVO, SAMPLE_ATIVO_2])
        response = client.get("/api/ativos")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_returns_total_count(self, client):
        client._mock_supabase.set_table_data("ativos", [SAMPLE_ATIVO])
        response = client.get("/api/ativos")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data

    def test_filter_by_carteira_id(self, client):
        client._mock_supabase.set_table_data("ativos", [SAMPLE_ATIVO])
        response = client.get("/api/ativos?carteira_id=cart-001")
        assert response.status_code == 200

    def test_requires_auth(self, client):
        response = client._tc.get("/api/ativos")
        assert response.status_code == 401


class TestAtivosPorCarteira:
    def test_returns_holdings_for_portfolio(self, client):
        client._mock_supabase.set_table_data("ativos", [SAMPLE_ATIVO, SAMPLE_FII])
        response = client.get("/api/ativos/por-carteira/cart-001")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/ativos/por-carteira/cart-001")
        assert response.status_code == 401


class TestObterAtivo:
    def test_returns_single_holding(self, client):
        client._mock_supabase.set_table_data("ativos", [SAMPLE_ATIVO])
        response = client.get("/api/ativos/ativo-001")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/ativos/ativo-001")
        assert response.status_code == 401


class TestCriarAtivo:
    def test_creates_holding(self, client):
        client._mock_supabase.set_table_data("ativos", [SAMPLE_ATIVO])
        response = client.post("/api/ativos", json={
            "carteira_id": "cart-001",
            "ticker": "PETR4",
            "nome": "Petrobras PN",
            "tipo": "acao",
            "setor": "Energia",
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_creates_fii_holding(self, client):
        client._mock_supabase.set_table_data("ativos", [SAMPLE_FII])
        response = client.post("/api/ativos", json={
            "carteira_id": "cart-001",
            "ticker": "HGLG11",
            "tipo": "fii",
        })
        assert response.status_code == 200

    def test_requires_carteira_id(self, client):
        response = client.post("/api/ativos", json={
            "ticker": "PETR4",
            "tipo": "acao",
        })
        assert response.status_code == 422

    def test_requires_ticker(self, client):
        response = client.post("/api/ativos", json={
            "carteira_id": "cart-001",
            "tipo": "acao",
        })
        assert response.status_code == 422

    def test_validates_tipo(self, client):
        response = client.post("/api/ativos", json={
            "carteira_id": "cart-001",
            "ticker": "PETR4",
            "tipo": "invalido",
        })
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/ativos", json={
            "carteira_id": "cart-001",
            "ticker": "PETR4",
            "tipo": "acao",
        })
        assert response.status_code == 401


class TestAtualizarAtivo:
    def test_updates_holding(self, client):
        updated = {**SAMPLE_ATIVO, "nome": "Petrobras Preferencial"}
        client._mock_supabase.set_table_data("ativos", [updated])
        response = client.patch("/api/ativos/ativo-001", json={"nome": "Petrobras Preferencial"})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_updates_setor(self, client):
        updated = {**SAMPLE_ATIVO, "setor": "Petroleo e Gas"}
        client._mock_supabase.set_table_data("ativos", [updated])
        response = client.patch("/api/ativos/ativo-001", json={"setor": "Petroleo e Gas"})
        assert response.status_code == 200

    def test_empty_update_returns_400(self, client):
        response = client.patch("/api/ativos/ativo-001", json={})
        assert response.status_code == 400

    def test_requires_auth(self, client):
        response = client._tc.patch("/api/ativos/ativo-001", json={"nome": "Teste"})
        assert response.status_code == 401


class TestExcluirAtivo:
    def test_deletes_holding(self, client):
        response = client.delete("/api/ativos/ativo-001")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "excluido" in data["message"]

    def test_requires_auth(self, client):
        response = client._tc.delete("/api/ativos/ativo-001")
        assert response.status_code == 401
