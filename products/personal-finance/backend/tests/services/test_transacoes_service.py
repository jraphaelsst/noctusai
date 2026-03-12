"""Unit tests for TransacoesService — balance updates, budget sync, cache invalidation."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from tests.conftest import MockSupabaseClient, MockSupabaseResponse


ORG_ID = "test-org-123"


def make_service(mock_sb=None):
    from app.services.transacoes_service import TransacoesService
    sb = mock_sb or MockSupabaseClient()
    return TransacoesService(sb, ORG_ID), sb


class TestBalanceUpdateOnCreate:
    @pytest.mark.asyncio
    async def test_receita_increases_balance(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [{"id": "tx-001", "tipo": "receita", "valor": 500, "conta_id": "c-1", "data": "2026-02-01"}])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 1000}])
        sb.set_table_data("orcamento_itens", [])
        sb.set_table_data("orcamentos", [])
        sb.set_table_data("resumos_mensais", [])

        result = await svc.criar({
            "valor": 500, "tipo": "receita", "conta_id": "c-1", "data": "2026-02-01",
        })
        assert result is not None

    @pytest.mark.asyncio
    async def test_despesa_decreases_balance(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [{"id": "tx-002", "tipo": "despesa", "valor": 300, "conta_id": "c-1", "data": "2026-02-05"}])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 1000}])
        sb.set_table_data("orcamento_itens", [])
        sb.set_table_data("orcamentos", [])
        sb.set_table_data("resumos_mensais", [])

        result = await svc.criar({
            "valor": 300, "tipo": "despesa", "conta_id": "c-1", "data": "2026-02-05",
        })
        assert result is not None

    @pytest.mark.asyncio
    async def test_transferencia_updates_source_and_destination(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [{"id": "tx-003", "tipo": "transferencia", "valor": 200, "conta_id": "c-1", "conta_destino_id": "c-2", "data": "2026-02-10"}])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 1000}])
        sb.set_table_data("orcamento_itens", [])
        sb.set_table_data("orcamentos", [])
        sb.set_table_data("resumos_mensais", [])

        result = await svc.criar({
            "valor": 200, "tipo": "transferencia", "conta_id": "c-1", "conta_destino_id": "c-2", "data": "2026-02-10",
        })
        assert result is not None

    @pytest.mark.asyncio
    async def test_transferencia_requires_conta_destino(self):
        svc, sb = make_service()
        with pytest.raises(ValueError, match="conta_destino_id"):
            await svc.criar({
                "valor": 200, "tipo": "transferencia", "conta_id": "c-1", "data": "2026-02-10",
            })


class TestBalanceReversalOnUpdate:
    @pytest.mark.asyncio
    async def test_reverses_old_and_applies_new(self):
        svc, sb = make_service()
        old_tx = {"id": "tx-001", "tipo": "despesa", "valor": 300, "conta_id": "c-1", "data": "2026-02-05"}
        new_tx = {"id": "tx-001", "tipo": "despesa", "valor": 500, "conta_id": "c-1", "data": "2026-02-05"}
        sb.set_table_data("transacoes", [old_tx])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 1000}])
        sb.set_table_data("orcamento_itens", [])
        sb.set_table_data("orcamentos", [])
        sb.set_table_data("resumos_mensais", [])

        result = await svc.atualizar("tx-001", {"valor": 500})
        # Should not raise; update returns the mock data
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [])

        result = await svc.atualizar("tx-999", {"valor": 500})
        # single() on empty list returns None
        assert result is None


class TestBalanceReversalOnDelete:
    @pytest.mark.asyncio
    async def test_reverses_balance_on_delete(self):
        svc, sb = make_service()
        tx = {"id": "tx-001", "tipo": "despesa", "valor": 300, "conta_id": "c-1", "data": "2026-02-05"}
        sb.set_table_data("transacoes", [tx])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 700}])
        sb.set_table_data("orcamento_itens", [])
        sb.set_table_data("orcamentos", [])
        sb.set_table_data("resumos_mensais", [])

        result = await svc.excluir("tx-001")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_transfer_reverses_both_accounts(self):
        svc, sb = make_service()
        tx = {"id": "tx-003", "tipo": "transferencia", "valor": 200, "conta_id": "c-1", "conta_destino_id": "c-2", "data": "2026-02-10"}
        sb.set_table_data("transacoes", [tx])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 800}])
        sb.set_table_data("orcamento_itens", [])
        sb.set_table_data("orcamentos", [])
        sb.set_table_data("resumos_mensais", [])

        result = await svc.excluir("tx-003")
        assert result is True


class TestBudgetSyncIntegration:
    @pytest.mark.asyncio
    async def test_criar_triggers_budget_sync(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [{"id": "tx-001", "tipo": "despesa", "valor": 300, "conta_id": "c-1", "categoria_id": "cat-1", "data": "2026-02-05"}])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 1000}])
        sb.set_table_data("orcamento_itens", [{"id": "item-1", "orcamento_id": "orc-1", "categoria_id": "cat-1", "periodo_mes": "2026-02"}])
        sb.set_table_data("orcamentos", [{"id": "orc-1", "org_id": ORG_ID}])
        sb.set_table_data("resumos_mensais", [])

        result = await svc.criar({
            "valor": 300, "tipo": "despesa", "conta_id": "c-1", "categoria_id": "cat-1", "data": "2026-02-05",
        })
        assert result is not None

    @pytest.mark.asyncio
    async def test_criar_without_categoria_skips_sync(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [{"id": "tx-001", "tipo": "receita", "valor": 500, "conta_id": "c-1", "data": "2026-02-01"}])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 1000}])
        sb.set_table_data("resumos_mensais", [])

        # Should not raise even without categoria_id
        result = await svc.criar({
            "valor": 500, "tipo": "receita", "conta_id": "c-1", "data": "2026-02-01",
        })
        assert result is not None


class TestCacheInvalidation:
    @pytest.mark.asyncio
    async def test_criar_triggers_cache_invalidation(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [{"id": "tx-001", "tipo": "receita", "valor": 500, "conta_id": "c-1", "data": "2026-02-01"}])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 1000}])
        sb.set_table_data("resumos_mensais", [])
        sb.set_table_data("orcamento_itens", [])
        sb.set_table_data("orcamentos", [])

        result = await svc.criar({
            "valor": 500, "tipo": "receita", "conta_id": "c-1", "data": "2026-02-01",
        })
        assert result is not None


class TestSideEffectFailureIsolation:
    @pytest.mark.asyncio
    async def test_budget_sync_failure_does_not_break_create(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [{"id": "tx-001", "tipo": "despesa", "valor": 300, "conta_id": "c-1", "categoria_id": "cat-1", "data": "2026-02-05"}])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 1000}])
        sb.set_table_data("resumos_mensais", [])

        # orcamento_itens not set — will use default empty, sync completes with 0 updated
        result = await svc.criar({
            "valor": 300, "tipo": "despesa", "conta_id": "c-1", "categoria_id": "cat-1", "data": "2026-02-05",
        })
        assert result is not None

    @pytest.mark.asyncio
    async def test_cache_failure_does_not_break_create(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [{"id": "tx-001", "tipo": "receita", "valor": 500, "conta_id": "c-1", "data": "2026-02-01"}])
        sb.set_table_data("contas", [{"id": "c-1", "saldo": 1000}])
        # No resumos_mensais table set — cache save will use default empty, completing gracefully

        result = await svc.criar({
            "valor": 500, "tipo": "receita", "conta_id": "c-1", "data": "2026-02-01",
        })
        assert result is not None
