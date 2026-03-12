"""Integration tests for Contas (accounts) — full CRUD cycles with stateful mock."""
import pytest


class TestContasCRUDCycle:
    def test_full_crud_cycle(self, integration_client):
        c = integration_client

        # Create
        resp = c.post("/api/contas", json={
            "nome": "Itau Corrente",
            "tipo": "corrente",
            "instituicao": "Itau",
            "saldo": 5000,
        })
        assert resp.status_code == 200
        conta = resp.json()["data"]
        conta_id = conta["id"]
        assert conta["nome"] == "Itau Corrente"

        # Read single
        resp = c.get(f"/api/contas/{conta_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["nome"] == "Itau Corrente"

        # List
        resp = c.get("/api/contas")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1

        # Update
        resp = c.patch(f"/api/contas/{conta_id}", json={"nome": "Itau Principal"})
        assert resp.status_code == 200
        assert resp.json()["data"]["nome"] == "Itau Principal"

        # Delete
        resp = c.delete(f"/api/contas/{conta_id}")
        assert resp.status_code == 200

    def test_create_multiple_accounts(self, integration_client):
        c = integration_client

        c.post("/api/contas", json={"nome": "Corrente", "tipo": "corrente", "saldo": 3000})
        c.post("/api/contas", json={"nome": "Poupanca", "tipo": "poupanca", "saldo": 10000})
        c.post("/api/contas", json={"nome": "Cartao", "tipo": "cartao_credito", "saldo": -500})

        resp = c.get("/api/contas")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 3


class TestContasSaldos:
    def test_saldos_endpoint(self, integration_client):
        c = integration_client

        c.post("/api/contas", json={"nome": "Corrente", "tipo": "corrente", "saldo": 5000})
        c.post("/api/contas", json={"nome": "Poupanca", "tipo": "poupanca", "saldo": 10000})

        resp = c.get("/api/contas/saldos")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2


class TestContasValidation:
    def test_invalid_tipo_rejected(self, integration_client):
        resp = integration_client.post("/api/contas", json={
            "nome": "Invalida",
            "tipo": "invalidtype",
        })
        assert resp.status_code == 422

    def test_missing_nome_rejected(self, integration_client):
        resp = integration_client.post("/api/contas", json={
            "tipo": "corrente",
        })
        assert resp.status_code == 422

    def test_empty_nome_rejected(self, integration_client):
        resp = integration_client.post("/api/contas", json={
            "nome": "",
            "tipo": "corrente",
        })
        assert resp.status_code == 422
