"""Tests for cotacoes (stock quotes) router."""
import pytest
from unittest.mock import patch


SAMPLE_COTACAO = {
    "ticker": "PETR4.SA",
    "preco": 38.50,
    "variacao": 1.20,
    "variacao_pct": 3.22,
    "volume": 15000000,
    "max_dia": 39.00,
    "min_dia": 37.80,
    "max_52s": 42.50,
    "min_52s": 28.10,
    "timestamp": "2026-03-01T12:00:00+00:00",
    "fonte": "dry-run",
}


class TestObterCotacao:
    def test_returns_quote(self, client):
        response = client.get("/api/cotacoes/PETR4.SA")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        result = data["data"]
        assert "ticker" in result
        assert "preco" in result

    def test_returns_dry_run_data(self, client):
        response = client.get("/api/cotacoes/VALE3.SA")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["ticker"] == "VALE3.SA"

    def test_requires_auth(self, client):
        response = client._tc.get("/api/cotacoes/PETR4.SA")
        assert response.status_code == 401


class TestCotacoesBatch:
    def test_returns_batch_quotes(self, client):
        response = client.post("/api/cotacoes/batch", json={
            "tickers": ["PETR4.SA", "VALE3.SA"],
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 2

    def test_empty_tickers(self, client):
        response = client.post("/api/cotacoes/batch", json={
            "tickers": [],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    def test_requires_tickers_field(self, client):
        response = client.post("/api/cotacoes/batch", json={})
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/cotacoes/batch", json={
            "tickers": ["PETR4.SA"],
        })
        assert response.status_code == 401


class TestAtualizarPrecos:
    def test_atualizar_all(self, client):
        client._mock_supabase.set_table_data("carteiras", [{"id": "cart-001"}])
        client._mock_supabase.set_table_data("ativos", [
            {"id": "a-001", "ticker": "PETR4.SA", "quantidade": 100, "preco_medio": 35.00},
        ])
        response = client.post("/api/cotacoes/atualizar")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_atualizar_with_carteira_id(self, client):
        client._mock_supabase.set_table_data("ativos", [
            {"id": "a-001", "ticker": "PETR4.SA", "quantidade": 100, "preco_medio": 35.00},
        ])
        response = client.post("/api/cotacoes/atualizar?carteira_id=cart-001")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.post("/api/cotacoes/atualizar")
        assert response.status_code == 401
