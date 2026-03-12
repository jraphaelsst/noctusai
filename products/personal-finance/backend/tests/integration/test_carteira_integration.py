"""Integration tests for Carteira (portfolio) — CRUD, assets, and summary."""
import pytest


ORG_ID = "test-org-123"


class TestCarteiraCRUDCycle:
    def test_full_crud_cycle(self, integration_client):
        c = integration_client

        # Create
        resp = c.post("/api/carteiras", json={
            "nome": "Renda Variavel",
            "tipo": "acoes",
            "corretora": "Clear",
        })
        assert resp.status_code == 200
        cart = resp.json()["data"]
        cart_id = cart["id"]

        # Read
        resp = c.get(f"/api/carteiras/{cart_id}")
        assert resp.status_code == 200

        # List
        resp = c.get("/api/carteiras")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1

        # Update
        resp = c.patch(f"/api/carteiras/{cart_id}", json={"nome": "Renda Variavel BR"})
        assert resp.status_code == 200

        # Delete
        resp = c.delete(f"/api/carteiras/{cart_id}")
        assert resp.status_code == 200


class TestCarteiraWithAtivos:
    def test_portfolio_with_holdings(self, integration_client):
        c = integration_client

        # Create portfolio
        resp = c.post("/api/carteiras", json={
            "nome": "Acoes BR",
            "tipo": "acoes",
        })
        cart_id = resp.json()["data"]["id"]

        # Create assets in the portfolio
        resp = c.post("/api/ativos", json={
            "carteira_id": cart_id,
            "ticker": "PETR4",
            "tipo": "acao",
        })
        assert resp.status_code == 200

        resp = c.post("/api/ativos", json={
            "carteira_id": cart_id,
            "ticker": "VALE3",
            "tipo": "acao",
        })
        assert resp.status_code == 200

        # List assets
        resp = c.get("/api/ativos", params={"carteira_id": cart_id})
        assert resp.status_code == 200

    def test_portfolio_summary(self, integration_client):
        c = integration_client

        c.seed("carteiras", [{
            "id": "cart-1",
            "org_id": ORG_ID,
            "nome": "Diversificada",
            "tipo": "geral",
            "ativo": True,
        }])
        c.seed("ativos", [
            {
                "id": "a1", "carteira_id": "cart-1", "ticker": "PETR4",
                "tipo": "acao", "valor_atual": 6000, "ganho_perda": 600,
                "preco_medio": 27, "quantidade": 200,
            },
            {
                "id": "a2", "carteira_id": "cart-1", "ticker": "KNRI11",
                "tipo": "fii", "valor_atual": 4000, "ganho_perda": -100,
                "preco_medio": 42, "quantidade": 100,
            },
        ])
        c.seed("alocacao_alvo", [])

        resp = c.get("/api/carteiras/cart-1/resumo")
        assert resp.status_code == 200
        resumo = resp.json()["data"]
        assert resumo["valor_total"] == 10000
        assert resumo["total_ativos"] == 2


class TestCarteiraValidation:
    def test_invalid_tipo_rejected(self, integration_client):
        resp = integration_client.post("/api/carteiras", json={
            "nome": "Invalida",
            "tipo": "invalido",
        })
        assert resp.status_code == 422

    def test_empty_nome_rejected(self, integration_client):
        resp = integration_client.post("/api/carteiras", json={
            "nome": "",
            "tipo": "acoes",
        })
        assert resp.status_code == 422
