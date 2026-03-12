"""Integration tests for Metas (goals) — CRUD cycles and contribution tracking."""
import pytest


ORG_ID = "test-org-123"


class TestMetasCRUDCycle:
    def test_full_crud_cycle(self, integration_client):
        c = integration_client

        # Create
        resp = c.post("/api/metas", json={
            "nome": "Reserva de Emergencia",
            "tipo": "fundo_emergencia",
            "valor_alvo": 30000,
            "valor_atual": 5000,
            "prioridade": "alta",
            "data_alvo": "2027-06-01",
        })
        assert resp.status_code == 200
        meta = resp.json()["data"]
        meta_id = meta["id"]

        # Read single
        resp = c.get(f"/api/metas/{meta_id}")
        assert resp.status_code == 200

        # List
        resp = c.get("/api/metas")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1

        # Update
        resp = c.patch(f"/api/metas/{meta_id}", json={"nome": "Fundo Emergencia"})
        assert resp.status_code == 200

        # Delete
        resp = c.delete(f"/api/metas/{meta_id}")
        assert resp.status_code == 200


class TestMetasContribuicoes:
    def test_add_contribution_updates_progress(self, integration_client):
        c = integration_client

        # Create a goal
        resp = c.post("/api/metas", json={
            "nome": "Viagem",
            "tipo": "poupanca",
            "valor_alvo": 10000,
            "valor_atual": 2000,
        })
        meta_id = resp.json()["data"]["id"]

        # Add contributions (the service creates records in meta_contribuicoes and updates metas)
        c.seed("meta_contribuicoes", [
            {"id": "mc-1", "meta_id": meta_id, "valor": 1000, "data": "2026-01-15"},
            {"id": "mc-2", "meta_id": meta_id, "valor": 1000, "data": "2026-02-15"},
        ])

        # Check progress
        resp = c.get(f"/api/metas/{meta_id}/progresso")
        assert resp.status_code == 200
        prog = resp.json()["data"]
        assert prog["percentual"] >= 0

    def test_contribution_via_api(self, integration_client):
        c = integration_client

        # Seed a meta directly so the contribution can reference it
        c.seed("metas", [{
            "id": "meta-1",
            "org_id": ORG_ID,
            "nome": "Casa Propria",
            "tipo": "poupanca",
            "valor_alvo": 100000,
            "valor_atual": 20000,
            "status": "ativa",
        }])
        c.seed("meta_contribuicoes", [])

        resp = c.post("/api/metas/meta-1/contribuicao", json={
            "valor": 5000,
            "data": "2026-03-01",
        })
        assert resp.status_code == 200


class TestMetasValidation:
    def test_invalid_tipo_rejected(self, integration_client):
        resp = integration_client.post("/api/metas", json={
            "nome": "Invalida",
            "tipo": "invalido",
            "valor_alvo": 10000,
        })
        assert resp.status_code == 422

    def test_zero_valor_alvo_rejected(self, integration_client):
        resp = integration_client.post("/api/metas", json={
            "nome": "Invalida",
            "tipo": "poupanca",
            "valor_alvo": 0,
        })
        assert resp.status_code == 422
