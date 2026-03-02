"""Tests for transacoes (transactions) router."""
import pytest


SAMPLE_TRANSACAO = {
    "id": "trans-001",
    "org_id": "test-org-123",
    "conta_id": "conta-001",
    "categoria_id": "cat-001",
    "data": "2026-02-15",
    "valor": 150.00,
    "tipo": "despesa",
    "descricao": "Supermercado",
    "comerciante": "Carrefour",
    "notas": None,
    "tags": [],
    "created_at": "2026-02-15T10:00:00",
}

SAMPLE_TRANSACAO_2 = {
    "id": "trans-002",
    "org_id": "test-org-123",
    "conta_id": "conta-001",
    "categoria_id": "cat-002",
    "data": "2026-02-20",
    "valor": 5000.00,
    "tipo": "receita",
    "descricao": "Salario",
    "comerciante": None,
    "notas": None,
    "tags": ["salario"],
    "created_at": "2026-02-20T10:00:00",
}


class TestListarTransacoes:
    def test_returns_paginated_list(self, client):
        client._mock_supabase.set_table_data("transacoes", [SAMPLE_TRANSACAO, SAMPLE_TRANSACAO_2])
        response = client.get("/api/transacoes")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "pagination" in data
        assert "page" in data["pagination"]
        assert "total" in data["pagination"]

    def test_filter_by_tipo(self, client):
        client._mock_supabase.set_table_data("transacoes", [SAMPLE_TRANSACAO])
        response = client.get("/api/transacoes?tipo=despesa")
        assert response.status_code == 200

    def test_filter_by_conta_id(self, client):
        client._mock_supabase.set_table_data("transacoes", [SAMPLE_TRANSACAO])
        response = client.get("/api/transacoes?conta_id=conta-001")
        assert response.status_code == 200

    def test_filter_by_date_range(self, client):
        client._mock_supabase.set_table_data("transacoes", [SAMPLE_TRANSACAO])
        response = client.get("/api/transacoes?data_inicio=2026-02-01&data_fim=2026-02-28")
        assert response.status_code == 200

    def test_pagination_params(self, client):
        client._mock_supabase.set_table_data("transacoes", [SAMPLE_TRANSACAO])
        response = client.get("/api/transacoes?page=2&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["page"] == 2
        assert data["pagination"]["page_size"] == 10

    def test_requires_auth(self, client):
        response = client._tc.get("/api/transacoes")
        assert response.status_code == 401


class TestTransacoesPorCategoria:
    def test_returns_grouped_by_category(self, client):
        client._mock_supabase.set_table_data("transacoes", [
            {
                "categoria_id": "cat-001",
                "valor": 100.00,
                "tipo": "despesa",
                "categoria": {"id": "cat-001", "nome": "Alimentacao", "icone": "", "cor": "#ef4444"},
            },
            {
                "categoria_id": "cat-001",
                "valor": 50.00,
                "tipo": "despesa",
                "categoria": {"id": "cat-001", "nome": "Alimentacao", "icone": "", "cor": "#ef4444"},
            },
        ])
        response = client.get("/api/transacoes/por-categoria?data_inicio=2026-02-01&data_fim=2026-02-28")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_date_params(self, client):
        response = client.get("/api/transacoes/por-categoria")
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.get("/api/transacoes/por-categoria?data_inicio=2026-02-01&data_fim=2026-02-28")
        assert response.status_code == 401


class TestObterTransacao:
    def test_returns_single_transaction(self, client):
        client._mock_supabase.set_table_data("transacoes", [SAMPLE_TRANSACAO])
        response = client.get("/api/transacoes/trans-001")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/transacoes/trans-001")
        assert response.status_code == 401


class TestCriarTransacao:
    def test_creates_transaction(self, client):
        client._mock_supabase.set_table_data("transacoes", [SAMPLE_TRANSACAO])
        # Also set contas data for balance update
        client._mock_supabase.set_table_data("contas", [{"id": "conta-001", "saldo": 5000.00}])
        response = client.post("/api/transacoes", json={
            "conta_id": "conta-001",
            "data": "2026-02-15",
            "valor": 150.00,
            "tipo": "despesa",
            "descricao": "Supermercado",
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_conta_id(self, client):
        response = client.post("/api/transacoes", json={
            "data": "2026-02-15",
            "valor": 150.00,
            "tipo": "despesa",
        })
        assert response.status_code == 422

    def test_validates_tipo(self, client):
        response = client.post("/api/transacoes", json={
            "conta_id": "conta-001",
            "data": "2026-02-15",
            "valor": 150.00,
            "tipo": "invalido",
        })
        assert response.status_code == 422

    def test_validates_data_format(self, client):
        response = client.post("/api/transacoes", json={
            "conta_id": "conta-001",
            "data": "15/02/2026",
            "valor": 150.00,
            "tipo": "despesa",
        })
        assert response.status_code == 422

    def test_valor_must_be_positive(self, client):
        response = client.post("/api/transacoes", json={
            "conta_id": "conta-001",
            "data": "2026-02-15",
            "valor": -50.00,
            "tipo": "despesa",
        })
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/transacoes", json={
            "conta_id": "conta-001",
            "data": "2026-02-15",
            "valor": 150.00,
            "tipo": "despesa",
        })
        assert response.status_code == 401


class TestAtualizarTransacao:
    def test_updates_transaction(self, client):
        updated = {**SAMPLE_TRANSACAO, "descricao": "Mercado Atualizado"}
        client._mock_supabase.set_table_data("transacoes", [updated])
        response = client.patch("/api/transacoes/trans-001", json={"descricao": "Mercado Atualizado"})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_empty_update_returns_400(self, client):
        response = client.patch("/api/transacoes/trans-001", json={})
        assert response.status_code == 400

    def test_requires_auth(self, client):
        response = client._tc.patch("/api/transacoes/trans-001", json={"descricao": "Teste"})
        assert response.status_code == 401


class TestExcluirTransacao:
    def test_deletes_transaction(self, client):
        response = client.delete("/api/transacoes/trans-001")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "excluida" in data["message"]

    def test_requires_auth(self, client):
        response = client._tc.delete("/api/transacoes/trans-001")
        assert response.status_code == 401
