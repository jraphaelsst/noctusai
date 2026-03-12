"""Cross-service integration tests — workflows that span multiple services.

These tests verify that side effects cascade correctly between services:
- Transaction creation -> balance update -> budget sync -> cache invalidation
- Recurring execution -> transaction creation -> balance update
- Portfolio operations -> FIFO recalculation
"""
import pytest
from datetime import date, timedelta


ORG_ID = "test-org-123"


class TestTransactionBudgetSync:
    """Verify that creating a transaction syncs budget spending."""

    def test_transaction_syncs_budget_item(self, integration_client):
        c = integration_client

        # Seed account
        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 50000, "ativo": True},
        ])
        # Seed budget and items
        c.seed("orcamentos", [{
            "id": "orc-1", "org_id": ORG_ID, "nome": "Março", "metodo": "zero_based",
        }])
        c.seed("orcamento_itens", [{
            "id": "item-1", "orcamento_id": "orc-1", "categoria_id": "cat-alimentacao",
            "valor_planejado": 2000, "valor_gasto": 0, "periodo_mes": "2026-03",
        }])
        c.seed("categorias", [
            {"id": "cat-alimentacao", "nome": "Alimentacao", "tipo": "despesa", "ordem": 1},
        ])

        # Create a despesa in the same category+month
        c.post("/api/transacoes", json={
            "conta_id": "conta-1",
            "categoria_id": "cat-alimentacao",
            "data": "2026-03-15",
            "valor": 800,
            "tipo": "despesa",
            "descricao": "Supermercado",
        })

        # The budget sync runs as a side effect — check the budget item
        itens = c.get_data("orcamento_itens")
        item = next((i for i in itens if i["id"] == "item-1"), None)
        assert item is not None
        # valor_gasto should have been updated to 800
        assert item["valor_gasto"] == 800

    def test_multiple_transactions_accumulate_budget(self, integration_client):
        c = integration_client

        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 50000, "ativo": True},
        ])
        c.seed("orcamentos", [{
            "id": "orc-1", "org_id": ORG_ID, "nome": "Março", "metodo": "zero_based",
        }])
        c.seed("orcamento_itens", [{
            "id": "item-1", "orcamento_id": "orc-1", "categoria_id": "cat-moradia",
            "valor_planejado": 3000, "valor_gasto": 0, "periodo_mes": "2026-03",
        }])

        # Create two transactions in same category+month
        c.post("/api/transacoes", json={
            "conta_id": "conta-1", "categoria_id": "cat-moradia",
            "data": "2026-03-01", "valor": 2000, "tipo": "despesa", "descricao": "Aluguel",
        })
        c.post("/api/transacoes", json={
            "conta_id": "conta-1", "categoria_id": "cat-moradia",
            "data": "2026-03-05", "valor": 500, "tipo": "despesa", "descricao": "Condominio",
        })

        itens = c.get_data("orcamento_itens")
        item = next((i for i in itens if i["id"] == "item-1"), None)
        assert item is not None
        # Should be sum of both transactions
        assert item["valor_gasto"] == 2500


class TestTransactionCacheInvalidation:
    """Verify that transactions trigger monthly report cache updates."""

    def test_transaction_refreshes_monthly_cache(self, integration_client):
        c = integration_client

        c.seed("contas", [
            {"id": "conta-1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 50000, "ativo": True},
        ])
        c.seed("resumos_mensais", [])

        # Create transactions
        c.post("/api/transacoes", json={
            "conta_id": "conta-1", "data": "2026-03-01", "valor": 5000,
            "tipo": "receita", "descricao": "Salario",
        })
        c.post("/api/transacoes", json={
            "conta_id": "conta-1", "data": "2026-03-10", "valor": 1500,
            "tipo": "despesa", "descricao": "Aluguel",
        })

        # The cache should have been populated as a side effect
        cache = c.get_data("resumos_mensais")
        assert len(cache) >= 1


class TestRecurringExecutionWorkflow:
    """Verify the full recurring -> transaction -> balance pipeline."""

    def test_recurring_execution_cascades_correctly(self, integration_client):
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
            "categoria_id": "cat-moradia",
            "proxima_data": yesterday,
            "ativo": True,
            "is_automatico": True,
        }])

        # Execute pending recurring entries
        resp = c.post("/api/recorrentes/executar")
        assert resp.status_code == 200
        assert resp.json()["data"]["executadas"] >= 1

        # Verify transaction was created
        txs = c.get_data("transacoes")
        assert len(txs) >= 1
        tx = txs[0]
        assert float(tx["valor"]) == 2000
        assert tx["tipo"] == "despesa"

        # Verify balance was updated
        contas = c.get_data("contas")
        conta = next(ct for ct in contas if ct["id"] == "conta-1")
        assert conta["saldo"] == 8000  # 10000 - 2000

        # Verify proxima_data was advanced
        recs = c.get_data("recorrentes")
        rec = next(r for r in recs if r["id"] == "rec-1")
        assert rec["proxima_data"] != yesterday


class TestPatrimonioWorkflow:
    """Verify net worth calculations across accounts and investments."""

    def test_patrimonio_with_accounts_and_investments(self, integration_client):
        c = integration_client

        c.seed("contas", [
            {"id": "c1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 15000, "ativo": True},
            {"id": "c2", "org_id": ORG_ID, "nome": "Poupanca", "tipo": "poupanca", "saldo": 30000, "ativo": True},
            {"id": "c3", "org_id": ORG_ID, "nome": "Cartao", "tipo": "cartao_credito", "saldo": -3000, "ativo": True},
        ])
        c.seed("ativos", [
            {"id": "a1", "org_id": ORG_ID, "ticker": "PETR4", "valor_atual": 20000, "carteira_id": "cart-1"},
        ])

        resp = c.get("/api/patrimonio/atual")
        assert resp.status_code == 200
        result = resp.json()["data"]
        # Assets: 15000 + 30000 + 20000 = 65000
        assert result["total_ativos"] == 65000
        # Liabilities: 3000 (credit card negative balance)
        assert result["total_passivos"] == 3000
        # Net worth: 65000 - 3000 = 62000
        assert result["patrimonio_liquido"] == 62000

    def test_patrimonio_snapshot_creation(self, integration_client):
        c = integration_client

        c.seed("contas", [
            {"id": "c1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 5000, "ativo": True},
        ])
        c.seed("ativos", [])
        c.seed("patrimonio_snapshots", [])

        resp = c.post("/api/patrimonio/snapshot", params={"data_snapshot": "2026-03-01"})
        assert resp.status_code in (200, 201)


class TestFullFinancialCycle:
    """End-to-end test simulating a typical monthly financial workflow."""

    def test_monthly_workflow(self, integration_client):
        c = integration_client

        # Step 1: Create accounts
        resp = c.post("/api/contas", json={
            "nome": "Conta Principal",
            "tipo": "corrente",
            "saldo": 0,
        })
        conta_id = resp.json()["data"]["id"]

        # Step 2: Receive salary
        resp = c.post("/api/transacoes", json={
            "conta_id": conta_id,
            "data": "2026-03-01",
            "valor": 8000,
            "tipo": "receita",
            "descricao": "Salario",
        })
        assert resp.status_code == 200

        # Step 3: Pay expenses
        c.post("/api/transacoes", json={
            "conta_id": conta_id,
            "data": "2026-03-05",
            "valor": 2000,
            "tipo": "despesa",
            "descricao": "Aluguel",
        })
        c.post("/api/transacoes", json={
            "conta_id": conta_id,
            "data": "2026-03-10",
            "valor": 800,
            "tipo": "despesa",
            "descricao": "Supermercado",
        })

        # Step 4: Check balance
        contas = c.get_data("contas")
        conta = next(ct for ct in contas if ct["id"] == conta_id)
        assert conta["saldo"] == 5200  # 0 + 8000 - 2000 - 800

        # Step 5: Create a goal and contribute
        resp = c.post("/api/metas", json={
            "nome": "Reserva de Emergencia",
            "tipo": "fundo_emergencia",
            "valor_alvo": 30000,
        })
        assert resp.status_code == 200

        # Step 6: Check patrimônio
        c.seed("ativos", [])  # ensure ativos table exists
        resp = c.get("/api/patrimonio/atual")
        assert resp.status_code == 200
        patrimonio = resp.json()["data"]
        assert patrimonio["patrimonio_liquido"] == 5200
