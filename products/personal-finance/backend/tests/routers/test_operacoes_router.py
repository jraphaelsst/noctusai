"""Tests for operacoes (investment operations) router."""
import pytest


SAMPLE_OPERACAO = {
    "id": "op-001",
    "carteira_id": "cart-001",
    "ativo_id": "ativo-001",
    "org_id": "test-org-123",
    "ticker": "PETR4",
    "tipo": "compra",
    "data": "2026-02-10",
    "quantidade": 100,
    "preco_unitario": 35.50,
    "taxas": 5.00,
    "valor_total": 3555.00,
    "notas": "Compra inicial",
    "created_at": "2026-02-10T10:00:00",
}

SAMPLE_OPERACAO_VENDA = {
    "id": "op-002",
    "carteira_id": "cart-001",
    "ativo_id": "ativo-001",
    "org_id": "test-org-123",
    "ticker": "PETR4",
    "tipo": "venda",
    "data": "2026-02-20",
    "quantidade": 50,
    "preco_unitario": 38.00,
    "taxas": 5.00,
    "valor_total": 1895.00,
    "notas": None,
    "created_at": "2026-02-20T10:00:00",
}

SAMPLE_OPERACAO_DIVIDENDO = {
    "id": "op-003",
    "carteira_id": "cart-001",
    "ativo_id": "ativo-001",
    "org_id": "test-org-123",
    "ticker": "PETR4",
    "tipo": "dividendo",
    "data": "2026-02-25",
    "quantidade": None,
    "preco_unitario": None,
    "taxas": 0,
    "valor_total": 75.00,
    "notas": "Dividendo Q4",
    "created_at": "2026-02-25T10:00:00",
}


class TestListarOperacoes:
    def test_returns_paginated_list(self, client):
        client._mock_supabase.set_table_data("operacoes", [SAMPLE_OPERACAO, SAMPLE_OPERACAO_VENDA])
        response = client.get("/api/operacoes")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "pagination" in data
        assert "page" in data["pagination"]
        assert "total" in data["pagination"]

    def test_filter_by_carteira_id(self, client):
        client._mock_supabase.set_table_data("operacoes", [SAMPLE_OPERACAO])
        response = client.get("/api/operacoes?carteira_id=cart-001")
        assert response.status_code == 200

    def test_filter_by_ativo_id(self, client):
        client._mock_supabase.set_table_data("operacoes", [SAMPLE_OPERACAO])
        response = client.get("/api/operacoes?ativo_id=ativo-001")
        assert response.status_code == 200

    def test_filter_by_ticker(self, client):
        client._mock_supabase.set_table_data("operacoes", [SAMPLE_OPERACAO])
        response = client.get("/api/operacoes?ticker=PETR4")
        assert response.status_code == 200

    def test_pagination_params(self, client):
        client._mock_supabase.set_table_data("operacoes", [SAMPLE_OPERACAO])
        response = client.get("/api/operacoes?page=1&page_size=25")
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 25

    def test_requires_auth(self, client):
        response = client._tc.get("/api/operacoes")
        assert response.status_code == 401


class TestOperacoesPorAtivo:
    def test_returns_operations_for_holding(self, client):
        client._mock_supabase.set_table_data("operacoes", [SAMPLE_OPERACAO, SAMPLE_OPERACAO_VENDA])
        response = client.get("/api/operacoes/por-ativo/ativo-001")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "pagination" in data

    def test_pagination_params(self, client):
        client._mock_supabase.set_table_data("operacoes", [SAMPLE_OPERACAO])
        response = client.get("/api/operacoes/por-ativo/ativo-001?page=1&page_size=10")
        assert response.status_code == 200

    def test_requires_auth(self, client):
        response = client._tc.get("/api/operacoes/por-ativo/ativo-001")
        assert response.status_code == 401


class TestObterOperacao:
    def test_returns_single_operation(self, client):
        client._mock_supabase.set_table_data("operacoes", [SAMPLE_OPERACAO])
        response = client.get("/api/operacoes/op-001")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/operacoes/op-001")
        assert response.status_code == 401


class TestCriarOperacao:
    def test_creates_buy_operation(self, client):
        client._mock_supabase.set_table_data("operacoes", [SAMPLE_OPERACAO])
        client._mock_supabase.set_table_data("ativos", [{
            "id": "ativo-001",
            "quantidade": 100,
            "preco_medio": 35.50,
            "preco_atual": 38.00,
            "valor_atual": 3800.00,
            "ganho_perda": 250.00,
        }])
        response = client.post("/api/operacoes", json={
            "carteira_id": "cart-001",
            "ativo_id": "ativo-001",
            "ticker": "PETR4",
            "tipo": "compra",
            "data": "2026-02-10",
            "quantidade": 100,
            "preco_unitario": 35.50,
            "valor_total": 3550.00,
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_creates_sell_operation(self, client):
        client._mock_supabase.set_table_data("operacoes", [SAMPLE_OPERACAO_VENDA])
        client._mock_supabase.set_table_data("ativos", [{
            "id": "ativo-001",
            "quantidade": 50,
            "preco_medio": 35.50,
            "preco_atual": 38.00,
            "valor_atual": 1900.00,
            "ganho_perda": 125.00,
        }])
        response = client.post("/api/operacoes", json={
            "carteira_id": "cart-001",
            "ativo_id": "ativo-001",
            "ticker": "PETR4",
            "tipo": "venda",
            "data": "2026-02-20",
            "quantidade": 50,
            "preco_unitario": 38.00,
            "valor_total": 1900.00,
        })
        assert response.status_code == 200

    def test_creates_dividend_operation(self, client):
        client._mock_supabase.set_table_data("operacoes", [SAMPLE_OPERACAO_DIVIDENDO])
        client._mock_supabase.set_table_data("ativos", [{
            "id": "ativo-001",
            "quantidade": 100,
            "preco_medio": 35.50,
            "preco_atual": 38.00,
        }])
        response = client.post("/api/operacoes", json={
            "carteira_id": "cart-001",
            "ativo_id": "ativo-001",
            "ticker": "PETR4",
            "tipo": "dividendo",
            "data": "2026-02-25",
            "valor_total": 75.00,
        })
        assert response.status_code == 200

    def test_requires_carteira_id(self, client):
        response = client.post("/api/operacoes", json={
            "ticker": "PETR4",
            "tipo": "compra",
            "data": "2026-02-10",
            "valor_total": 3550.00,
        })
        assert response.status_code == 422

    def test_requires_ticker(self, client):
        response = client.post("/api/operacoes", json={
            "carteira_id": "cart-001",
            "tipo": "compra",
            "data": "2026-02-10",
            "valor_total": 3550.00,
        })
        assert response.status_code == 422

    def test_validates_tipo(self, client):
        response = client.post("/api/operacoes", json={
            "carteira_id": "cart-001",
            "ticker": "PETR4",
            "tipo": "invalido",
            "data": "2026-02-10",
            "valor_total": 3550.00,
        })
        assert response.status_code == 422

    def test_validates_data_format(self, client):
        response = client.post("/api/operacoes", json={
            "carteira_id": "cart-001",
            "ticker": "PETR4",
            "tipo": "compra",
            "data": "10/02/2026",
            "valor_total": 3550.00,
        })
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/operacoes", json={
            "carteira_id": "cart-001",
            "ticker": "PETR4",
            "tipo": "compra",
            "data": "2026-02-10",
            "valor_total": 3550.00,
        })
        assert response.status_code == 401


class TestExcluirOperacao:
    def test_deletes_operation(self, client):
        client._mock_supabase.set_table_data("operacoes", [SAMPLE_OPERACAO])
        response = client.delete("/api/operacoes/op-001")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "excluida" in data["message"]

    def test_requires_auth(self, client):
        response = client._tc.delete("/api/operacoes/op-001")
        assert response.status_code == 401
