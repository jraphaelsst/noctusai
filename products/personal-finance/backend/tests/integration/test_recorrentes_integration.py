"""Integration tests for Recorrentes — recurring transaction execution workflow."""
import pytest
from datetime import date, timedelta


ORG_ID = "test-org-123"


class TestRecorrentesCRUDCycle:
    def test_full_crud_cycle(self, integration_client):
        c = integration_client

        # Create
        resp = c.post("/api/recorrentes", json={
            "nome": "Netflix",
            "valor": 55.90,
            "tipo": "despesa",
            "frequencia": "mensal",
            "conta_id": "conta-1",
            "proxima_data": "2026-04-01",
        })
        assert resp.status_code == 200
        rec = resp.json()["data"]
        rec_id = rec["id"]

        # Read
        resp = c.get(f"/api/recorrentes/{rec_id}")
        assert resp.status_code == 200

        # List
        resp = c.get("/api/recorrentes")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1

        # Update
        resp = c.patch(f"/api/recorrentes/{rec_id}", json={"valor": 59.90})
        assert resp.status_code == 200

        # Delete
        resp = c.delete(f"/api/recorrentes/{rec_id}")
        assert resp.status_code == 200


class TestRecorrentesExecution:
    def test_executar_pendentes_creates_transactions(self, integration_client):
        c = integration_client

        yesterday = (date.today() - timedelta(days=1)).isoformat()

        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 10000, "ativo": True},
        ])
        c.seed("recorrentes", [{
            "id": "rec-1",
            "org_id": ORG_ID,
            "nome": "Aluguel",
            "valor": 2000,
            "tipo": "despesa",
            "frequencia": "mensal",
            "conta_id": "conta-1",
            "proxima_data": yesterday,
            "ativo": True,
            "is_automatico": True,
        }])

        resp = c.post("/api/recorrentes/executar")
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert result["executadas"] >= 1

        # Verify transaction was created
        txs = c.get_data("transacoes")
        assert len(txs) >= 1

    def test_executar_unico(self, integration_client):
        c = integration_client

        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 5000, "ativo": True},
        ])
        c.seed("recorrentes", [{
            "id": "rec-1",
            "org_id": ORG_ID,
            "nome": "Spotify",
            "valor": 34.90,
            "tipo": "despesa",
            "frequencia": "mensal",
            "conta_id": "conta-1",
            "proxima_data": "2026-04-01",
            "ativo": True,
            "is_automatico": False,
        }])

        resp = c.post("/api/recorrentes/rec-1/executar")
        assert resp.status_code == 200

        # Verify transaction was created
        txs = c.get_data("transacoes")
        assert len(txs) >= 1

    def test_execution_updates_balance(self, integration_client):
        c = integration_client

        yesterday = (date.today() - timedelta(days=1)).isoformat()

        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 10000, "ativo": True},
        ])
        c.seed("recorrentes", [{
            "id": "rec-1",
            "org_id": ORG_ID,
            "nome": "Internet",
            "valor": 150,
            "tipo": "despesa",
            "frequencia": "mensal",
            "conta_id": "conta-1",
            "proxima_data": yesterday,
            "ativo": True,
            "is_automatico": True,
        }])

        c.post("/api/recorrentes/executar")

        # Balance should decrease
        contas = c.get_data("contas")
        conta = next(ct for ct in contas if ct["id"] == "conta-1")
        assert conta["saldo"] < 10000

    def test_skips_future_recorrentes(self, integration_client):
        c = integration_client

        future = (date.today() + timedelta(days=30)).isoformat()

        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 5000, "ativo": True},
        ])
        c.seed("recorrentes", [{
            "id": "rec-1",
            "org_id": ORG_ID,
            "nome": "Futura",
            "valor": 100,
            "tipo": "despesa",
            "frequencia": "mensal",
            "conta_id": "conta-1",
            "proxima_data": future,
            "ativo": True,
            "is_automatico": True,
        }])

        resp = c.post("/api/recorrentes/executar")
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert result["executadas"] == 0


class TestRecorrentesValidation:
    def test_invalid_frequencia_rejected(self, integration_client):
        resp = integration_client.post("/api/recorrentes", json={
            "nome": "Invalido",
            "valor": 100,
            "tipo": "despesa",
            "frequencia": "diaria",
        })
        assert resp.status_code == 422

    def test_invalid_tipo_rejected(self, integration_client):
        resp = integration_client.post("/api/recorrentes", json={
            "nome": "Invalido",
            "valor": 100,
            "tipo": "investimento",
            "frequencia": "mensal",
        })
        assert resp.status_code == 422
