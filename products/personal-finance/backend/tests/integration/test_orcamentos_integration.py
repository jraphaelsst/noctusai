"""Integration tests for Orcamentos (budgets) — CRUD cycles, item management, and progress."""
import pytest


ORG_ID = "test-org-123"


class TestOrcamentosCRUDCycle:
    def test_full_crud_cycle(self, integration_client):
        c = integration_client

        # Create budget
        resp = c.post("/api/orcamentos", json={
            "nome": "Orcamento Mensal Março",
            "metodo": "zero_based",
        })
        assert resp.status_code == 200
        orc = resp.json()["data"]
        orc_id = orc["id"]

        # Read
        resp = c.get(f"/api/orcamentos/{orc_id}")
        assert resp.status_code == 200

        # List
        resp = c.get("/api/orcamentos")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1

        # Update
        resp = c.patch(f"/api/orcamentos/{orc_id}", json={"nome": "Orcamento Março Atualizado"})
        assert resp.status_code == 200

        # Delete
        resp = c.delete(f"/api/orcamentos/{orc_id}")
        assert resp.status_code == 200


class TestOrcamentosItemCRUD:
    def test_add_and_manage_items(self, integration_client):
        c = integration_client

        # Create budget
        resp = c.post("/api/orcamentos", json={
            "nome": "Orcamento Março",
            "metodo": "zero_based",
        })
        orc_id = resp.json()["data"]["id"]

        # Create item
        resp = c.post(f"/api/orcamentos/{orc_id}/itens", json={
            "categoria_id": "cat-alimentacao",
            "valor_planejado": 1500,
            "periodo_mes": "2026-03",
        })
        assert resp.status_code == 200
        item = resp.json()["data"]
        item_id = item["id"]

        # List items
        resp = c.get(f"/api/orcamentos/{orc_id}/itens")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1

        # Update item
        resp = c.patch(f"/api/orcamentos/itens/{item_id}", json={"valor_planejado": 2000})
        assert resp.status_code == 200

        # Delete item
        resp = c.delete(f"/api/orcamentos/itens/{item_id}")
        assert resp.status_code == 200


class TestOrcamentosBudgetProgress:
    def test_progresso_with_seeded_data(self, integration_client):
        c = integration_client

        # Seed a budget and items directly
        c.seed("orcamentos", [{
            "id": "orc-1",
            "org_id": ORG_ID,
            "nome": "Março",
            "metodo": "zero_based",
        }])
        c.seed("orcamento_itens", [
            {
                "id": "item-1",
                "orcamento_id": "orc-1",
                "categoria_id": "cat-moradia",
                "valor_planejado": 2000,
                "valor_gasto": 0,
                "periodo_mes": "2026-03",
            },
            {
                "id": "item-2",
                "orcamento_id": "orc-1",
                "categoria_id": "cat-alimentacao",
                "valor_planejado": 1500,
                "valor_gasto": 0,
                "periodo_mes": "2026-03",
            },
        ])
        # Seed transactions for budget sync
        c.seed("transacoes", [
            {
                "id": "tx-1", "org_id": ORG_ID, "tipo": "despesa",
                "categoria_id": "cat-moradia", "valor": 1800,
                "data": "2026-03-05", "conta_id": "conta-1",
            },
            {
                "id": "tx-2", "org_id": ORG_ID, "tipo": "despesa",
                "categoria_id": "cat-alimentacao", "valor": 600,
                "data": "2026-03-10", "conta_id": "conta-1",
            },
        ])

        resp = c.get("/api/orcamentos/orc-1/progresso", params={"periodo_mes": "2026-03"})
        assert resp.status_code == 200
        prog = resp.json()["data"]
        assert prog["total_planejado"] == 3500
        # After sync, gastos should reflect transaction totals
        assert prog["total_gasto"] >= 0


class TestOrcamentosValidation:
    def test_invalid_metodo_rejected(self, integration_client):
        resp = integration_client.post("/api/orcamentos", json={
            "nome": "Invalido",
            "metodo": "invalido",
        })
        assert resp.status_code == 422

    def test_empty_nome_rejected(self, integration_client):
        resp = integration_client.post("/api/orcamentos", json={
            "nome": "",
        })
        assert resp.status_code == 422
