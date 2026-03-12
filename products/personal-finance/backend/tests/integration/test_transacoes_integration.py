"""Integration tests for Transacoes — CRUD cycles, balance updates, and side effects."""
import pytest


ORG_ID = "test-org-123"


class TestTransacoesCRUDCycle:
    def test_full_crud_cycle(self, integration_client):
        c = integration_client

        # Seed an account for the transaction
        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 5000, "ativo": True},
        ])

        # Create
        resp = c.post("/api/transacoes", json={
            "conta_id": "conta-1",
            "data": "2026-03-01",
            "valor": 1500,
            "tipo": "despesa",
            "descricao": "Aluguel",
        })
        assert resp.status_code == 200
        tx = resp.json()["data"]
        tx_id = tx["id"]

        # Read single
        resp = c.get(f"/api/transacoes/{tx_id}")
        assert resp.status_code == 200

        # List
        resp = c.get("/api/transacoes")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1

        # Update
        resp = c.patch(f"/api/transacoes/{tx_id}", json={"descricao": "Aluguel Atualizado"})
        assert resp.status_code == 200

        # Delete
        resp = c.delete(f"/api/transacoes/{tx_id}")
        assert resp.status_code == 200


class TestTransacoesBalanceUpdate:
    def test_receita_increases_balance(self, integration_client):
        c = integration_client

        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 5000, "ativo": True},
        ])

        c.post("/api/transacoes", json={
            "conta_id": "conta-1",
            "data": "2026-03-01",
            "valor": 3000,
            "tipo": "receita",
            "descricao": "Salario",
        })

        # Check that balance was updated in the stateful store
        contas = c.get_data("contas")
        conta = next(ct for ct in contas if ct["id"] == "conta-1")
        assert conta["saldo"] == 8000  # 5000 + 3000

    def test_despesa_decreases_balance(self, integration_client):
        c = integration_client

        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 5000, "ativo": True},
        ])

        c.post("/api/transacoes", json={
            "conta_id": "conta-1",
            "data": "2026-03-01",
            "valor": 1500,
            "tipo": "despesa",
            "descricao": "Aluguel",
        })

        contas = c.get_data("contas")
        conta = next(ct for ct in contas if ct["id"] == "conta-1")
        assert conta["saldo"] == 3500  # 5000 - 1500

    def test_multiple_transactions_compound(self, integration_client):
        c = integration_client

        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 10000, "ativo": True},
        ])

        c.post("/api/transacoes", json={
            "conta_id": "conta-1", "data": "2026-03-01", "valor": 5000,
            "tipo": "receita", "descricao": "Salario",
        })
        c.post("/api/transacoes", json={
            "conta_id": "conta-1", "data": "2026-03-05", "valor": 2000,
            "tipo": "despesa", "descricao": "Aluguel",
        })
        c.post("/api/transacoes", json={
            "conta_id": "conta-1", "data": "2026-03-10", "valor": 500,
            "tipo": "despesa", "descricao": "Mercado",
        })

        contas = c.get_data("contas")
        conta = next(ct for ct in contas if ct["id"] == "conta-1")
        assert conta["saldo"] == 12500  # 10000 + 5000 - 2000 - 500


class TestTransacoesTransferencia:
    def test_transfer_updates_both_accounts(self, integration_client):
        c = integration_client

        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 5000, "ativo": True},
            {"id": "conta-2", "org_id": ORG_ID, "nome": "Poupanca", "tipo": "poupanca", "saldo": 10000, "ativo": True},
        ])

        c.post("/api/transacoes", json={
            "conta_id": "conta-1",
            "conta_destino_id": "conta-2",
            "data": "2026-03-01",
            "valor": 2000,
            "tipo": "transferencia",
            "descricao": "Transferencia para poupanca",
        })

        contas = c.get_data("contas")
        corrente = next(ct for ct in contas if ct["id"] == "conta-1")
        poupanca = next(ct for ct in contas if ct["id"] == "conta-2")

        assert corrente["saldo"] == 3000  # 5000 - 2000
        assert poupanca["saldo"] == 12000  # 10000 + 2000


class TestTransacoesFilters:
    def test_list_with_pagination(self, integration_client):
        c = integration_client

        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 50000, "ativo": True},
        ])

        # Create several transactions
        for i in range(5):
            c.post("/api/transacoes", json={
                "conta_id": "conta-1",
                "data": f"2026-03-{i+1:02d}",
                "valor": 100 * (i + 1),
                "tipo": "despesa",
                "descricao": f"Transacao {i+1}",
            })

        resp = c.get("/api/transacoes", params={"page": 1, "page_size": 2})
        assert resp.status_code == 200

    def test_filter_by_tipo(self, integration_client):
        c = integration_client

        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 50000, "ativo": True},
        ])

        c.post("/api/transacoes", json={
            "conta_id": "conta-1", "data": "2026-03-01", "valor": 5000,
            "tipo": "receita", "descricao": "Salario",
        })
        c.post("/api/transacoes", json={
            "conta_id": "conta-1", "data": "2026-03-05", "valor": 1000,
            "tipo": "despesa", "descricao": "Mercado",
        })

        resp = c.get("/api/transacoes", params={"tipo": "receita"})
        assert resp.status_code == 200


class TestTransacoesValidation:
    def test_transfer_without_destination_rejected(self, integration_client):
        c = integration_client

        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 5000, "ativo": True},
        ])

        # Service raises ValueError which propagates through middleware
        with pytest.raises(Exception):
            c.post("/api/transacoes", json={
                "conta_id": "conta-1",
                "data": "2026-03-01",
                "valor": 1000,
                "tipo": "transferencia",
                "descricao": "Transferencia invalida",
            })

    def test_invalid_tipo_rejected(self, integration_client):
        resp = integration_client.post("/api/transacoes", json={
            "conta_id": "conta-1",
            "data": "2026-03-01",
            "valor": 1000,
            "tipo": "invalido",
        })
        assert resp.status_code == 422

    def test_negative_valor_rejected(self, integration_client):
        resp = integration_client.post("/api/transacoes", json={
            "conta_id": "conta-1",
            "data": "2026-03-01",
            "valor": -500,
            "tipo": "despesa",
        })
        assert resp.status_code == 422
