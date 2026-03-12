"""Tests for carteira (investment portfolio) router."""
import pytest


SAMPLE_CARTEIRA = {
    "id": "cart-001",
    "org_id": "test-org-123",
    "nome": "Carteira Principal",
    "tipo": "geral",
    "corretora": "XP Investimentos",
    "ativo": True,
    "created_at": "2026-01-01T10:00:00",
}

SAMPLE_CARTEIRA_2 = {
    "id": "cart-002",
    "org_id": "test-org-123",
    "nome": "Renda Fixa",
    "tipo": "renda_fixa",
    "corretora": "Nubank",
    "ativo": True,
    "created_at": "2026-01-10T10:00:00",
}

SAMPLE_ATIVO_HOLDING = {
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
}


class TestListarCarteiras:
    def test_returns_portfolios_list(self, client):
        client._mock_supabase.set_table_data("carteiras", [SAMPLE_CARTEIRA])
        client._mock_supabase.set_table_data("ativos", [SAMPLE_ATIVO_HOLDING])
        response = client.get("/api/carteiras")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_returns_total_count(self, client):
        client._mock_supabase.set_table_data("carteiras", [SAMPLE_CARTEIRA])
        client._mock_supabase.set_table_data("ativos", [])
        response = client.get("/api/carteiras")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/carteiras")
        assert response.status_code == 401


class TestObterCarteira:
    def test_returns_single_portfolio(self, client):
        client._mock_supabase.set_table_data("carteiras", [SAMPLE_CARTEIRA])
        response = client.get("/api/carteiras/cart-001")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/carteiras/cart-001")
        assert response.status_code == 401


class TestResumoCarteira:
    def test_returns_portfolio_summary(self, client):
        client._mock_supabase.set_table_data("carteiras", [SAMPLE_CARTEIRA])
        client._mock_supabase.set_table_data("ativos", [SAMPLE_ATIVO_HOLDING])
        client._mock_supabase.set_table_data("alocacao_alvo", [])
        response = client.get("/api/carteiras/cart-001/resumo")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/carteiras/cart-001/resumo")
        assert response.status_code == 401


class TestCriarCarteira:
    def test_creates_portfolio(self, client):
        client._mock_supabase.set_table_data("carteiras", [SAMPLE_CARTEIRA])
        response = client.post("/api/carteiras", json={
            "nome": "Carteira Principal",
            "tipo": "geral",
            "corretora": "XP Investimentos",
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_creates_with_minimum_fields(self, client):
        client._mock_supabase.set_table_data("carteiras", [SAMPLE_CARTEIRA])
        response = client.post("/api/carteiras", json={
            "nome": "Minha Carteira",
        })
        assert response.status_code == 200

    def test_requires_nome(self, client):
        response = client.post("/api/carteiras", json={
            "tipo": "geral",
        })
        assert response.status_code == 422

    def test_validates_tipo(self, client):
        response = client.post("/api/carteiras", json={
            "nome": "Carteira",
            "tipo": "invalido",
        })
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/carteiras", json={
            "nome": "Carteira Principal",
        })
        assert response.status_code == 401


class TestAtualizarCarteira:
    def test_updates_portfolio(self, client):
        updated = {**SAMPLE_CARTEIRA, "nome": "Carteira Atualizada"}
        client._mock_supabase.set_table_data("carteiras", [updated])
        response = client.patch("/api/carteiras/cart-001", json={"nome": "Carteira Atualizada"})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_updates_corretora(self, client):
        updated = {**SAMPLE_CARTEIRA, "corretora": "BTG Pactual"}
        client._mock_supabase.set_table_data("carteiras", [updated])
        response = client.patch("/api/carteiras/cart-001", json={"corretora": "BTG Pactual"})
        assert response.status_code == 200

    def test_empty_update_returns_400(self, client):
        response = client.patch("/api/carteiras/cart-001", json={})
        assert response.status_code == 400

    def test_requires_auth(self, client):
        response = client._tc.patch("/api/carteiras/cart-001", json={"nome": "Teste"})
        assert response.status_code == 401


class TestExcluirCarteira:
    def test_deletes_portfolio(self, client):
        client._mock_supabase.set_table_data("carteiras", [{"id": "cart-001", "org_id": "test-org-123"}])
        response = client.delete("/api/carteiras/cart-001")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "excluida" in data["message"]

    def test_requires_auth(self, client):
        response = client._tc.delete("/api/carteiras/cart-001")
        assert response.status_code == 401


class TestDefinirAlocacaoAlvo:
    def test_creates_target_allocation(self, client):
        client._mock_supabase.set_table_data("carteiras", [{"id": "cart-001"}])
        client._mock_supabase.set_table_data("alocacao_alvo", [{
            "id": "aloc-001",
            "carteira_id": "cart-001",
            "classe_ativo": "Acoes",
            "percentual_alvo": 60.0,
            "limite_desvio": 5.0,
        }])
        response = client.post("/api/carteiras/cart-001/alocacao", json={
            "classe_ativo": "Acoes",
            "percentual_alvo": 60.0,
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_validates_percentual_range(self, client):
        response = client.post("/api/carteiras/cart-001/alocacao", json={
            "classe_ativo": "Acoes",
            "percentual_alvo": 150.0,
        })
        assert response.status_code == 422

    def test_requires_classe_ativo(self, client):
        response = client.post("/api/carteiras/cart-001/alocacao", json={
            "percentual_alvo": 60.0,
        })
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/carteiras/cart-001/alocacao", json={
            "classe_ativo": "Acoes",
            "percentual_alvo": 60.0,
        })
        assert response.status_code == 401
