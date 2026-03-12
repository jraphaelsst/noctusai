"""Tests for watchlist router."""
import pytest


SAMPLE_WATCHLIST = {
    "id": "wl-001",
    "org_id": "test-org-123",
    "nome": "Acoes BR",
    "created_at": "2026-01-01T10:00:00",
}

SAMPLE_WATCHLIST_2 = {
    "id": "wl-002",
    "org_id": "test-org-123",
    "nome": "ETFs Internacionais",
    "created_at": "2026-01-02T10:00:00",
}

SAMPLE_ITEM = {
    "id": "wli-001",
    "watchlist_id": "wl-001",
    "ticker": "PETR4",
    "nome": "Petrobras PN",
    "alerta_preco_acima": 40.0,
    "alerta_preco_abaixo": 25.0,
    "notas": "Acompanhar resultados",
}


class TestListarWatchlists:
    def test_returns_list(self, client):
        client._mock_supabase.set_table_data("watchlists", [SAMPLE_WATCHLIST, SAMPLE_WATCHLIST_2])
        response = client.get("/api/watchlists")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_returns_total(self, client):
        client._mock_supabase.set_table_data("watchlists", [SAMPLE_WATCHLIST])
        response = client.get("/api/watchlists")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data

    def test_empty_list(self, client):
        client._mock_supabase.set_table_data("watchlists", [])
        response = client.get("/api/watchlists")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    def test_requires_auth(self, client):
        response = client._tc.get("/api/watchlists")
        assert response.status_code == 401


class TestObterWatchlist:
    def test_returns_single(self, client):
        client._mock_supabase.set_table_data("watchlists", [SAMPLE_WATCHLIST])
        client._mock_supabase.set_table_data("watchlist_itens", [SAMPLE_ITEM])
        response = client.get("/api/watchlists/wl-001")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_includes_itens(self, client):
        client._mock_supabase.set_table_data("watchlists", [SAMPLE_WATCHLIST])
        client._mock_supabase.set_table_data("watchlist_itens", [SAMPLE_ITEM])
        response = client.get("/api/watchlists/wl-001")
        assert response.status_code == 200
        data = response.json()
        assert "itens" in data["data"]

    def test_requires_auth(self, client):
        response = client._tc.get("/api/watchlists/wl-001")
        assert response.status_code == 401


class TestCriarWatchlist:
    def test_creates_watchlist(self, client):
        client._mock_supabase.set_table_data("watchlists", [SAMPLE_WATCHLIST])
        response = client.post("/api/watchlists", json={"nome": "Nova Lista"})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_nome(self, client):
        response = client.post("/api/watchlists", json={})
        assert response.status_code == 422

    def test_nome_min_length(self, client):
        response = client.post("/api/watchlists", json={"nome": ""})
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/watchlists", json={"nome": "Lista"})
        assert response.status_code == 401


class TestExcluirWatchlist:
    def test_deletes_watchlist(self, client):
        client._mock_supabase.set_table_data("watchlists", [SAMPLE_WATCHLIST])
        response = client.delete("/api/watchlists/wl-001")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_requires_auth(self, client):
        response = client._tc.delete("/api/watchlists/wl-001")
        assert response.status_code == 401


class TestAdicionarItem:
    def test_adds_item(self, client):
        client._mock_supabase.set_table_data("watchlists", [SAMPLE_WATCHLIST])
        client._mock_supabase.set_table_data("watchlist_itens", [SAMPLE_ITEM])
        response = client.post("/api/watchlists/wl-001/itens", json={
            "ticker": "VALE3",
            "nome": "Vale",
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_with_alerts(self, client):
        client._mock_supabase.set_table_data("watchlists", [SAMPLE_WATCHLIST])
        client._mock_supabase.set_table_data("watchlist_itens", [SAMPLE_ITEM])
        response = client.post("/api/watchlists/wl-001/itens", json={
            "ticker": "ITUB4",
            "alerta_preco_acima": 35.0,
            "alerta_preco_abaixo": 20.0,
        })
        assert response.status_code == 200

    def test_requires_ticker(self, client):
        client._mock_supabase.set_table_data("watchlists", [SAMPLE_WATCHLIST])
        response = client.post("/api/watchlists/wl-001/itens", json={
            "nome": "Sem Ticker",
        })
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/watchlists/wl-001/itens", json={
            "ticker": "VALE3",
        })
        assert response.status_code == 401


class TestRemoverItem:
    def test_removes_item(self, client):
        client._mock_supabase.set_table_data("watchlist_itens", [SAMPLE_ITEM])
        client._mock_supabase.set_table_data("watchlists", [SAMPLE_WATCHLIST])
        response = client.delete("/api/watchlists/itens/wli-001")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_requires_auth(self, client):
        response = client._tc.delete("/api/watchlists/itens/wli-001")
        assert response.status_code == 401
