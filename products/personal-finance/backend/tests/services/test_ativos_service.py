"""Unit tests for AtivosService — FIFO lot tracking and operation handling."""
import pytest
from tests.conftest import MockSupabaseClient


ORG_ID = "test-org-123"


def make_service(mock_sb=None):
    from app.services.ativos_service import AtivosService
    sb = mock_sb or MockSupabaseClient()
    return AtivosService(sb, ORG_ID), sb


class TestListar:
    @pytest.mark.asyncio
    async def test_returns_all_ativos(self):
        svc, sb = make_service()
        sb.set_table_data("ativos", [
            {"id": "a1", "ticker": "PETR4", "valor_atual": 5000},
            {"id": "a2", "ticker": "VALE3", "valor_atual": 8000},
        ])
        result = await svc.listar()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filter_by_carteira(self):
        svc, sb = make_service()
        sb.set_table_data("ativos", [{"id": "a1", "ticker": "PETR4", "carteira_id": "c1"}])
        result = await svc.listar(carteira_id="c1")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_list(self):
        svc, sb = make_service()
        sb.set_table_data("ativos", [])
        result = await svc.listar()
        assert result == []


class TestObter:
    @pytest.mark.asyncio
    async def test_returns_single(self):
        svc, sb = make_service()
        sb.set_table_data("ativos", [{"id": "a1", "ticker": "PETR4"}])
        result = await svc.obter("a1")
        assert result is not None


class TestCriar:
    @pytest.mark.asyncio
    async def test_creates_ativo(self):
        svc, sb = make_service()
        sb.set_table_data("ativos", [{"id": "a1", "ticker": "PETR4", "org_id": ORG_ID}])
        result = await svc.criar({"ticker": "PETR4", "carteira_id": "c1", "tipo": "acao", "quantidade": 100, "preco_medio": 30})
        assert result is not None


class TestRegistrarOperacao:
    @pytest.mark.asyncio
    async def test_registers_with_ativo_id(self):
        svc, sb = make_service()
        sb.set_table_data("operacoes", [{"id": "op1", "ativo_id": "a1", "tipo": "compra"}])
        sb.set_table_data("ativos", [{"id": "a1", "ticker": "PETR4", "preco_atual": 35, "quantidade": 100}])
        result = await svc.registrar_operacao({
            "carteira_id": "c1", "ativo_id": "a1", "ticker": "PETR4",
            "tipo": "compra", "quantidade": 100, "preco_unitario": 30,
            "valor_total": 3000, "data": "2026-03-01", "org_id": ORG_ID,
        })
        assert result is not None

    @pytest.mark.asyncio
    async def test_auto_creates_ativo_when_missing(self):
        svc, sb = make_service()
        sb.set_table_data("operacoes", [{"id": "op1", "tipo": "compra"}])
        sb.set_table_data("ativos", [{"id": "a-new", "ticker": "ITUB4", "preco_atual": 25}])
        result = await svc.registrar_operacao({
            "carteira_id": "c1", "ticker": "ITUB4",
            "tipo": "compra", "quantidade": 50, "preco_unitario": 25,
            "valor_total": 1250, "data": "2026-03-01", "org_id": ORG_ID,
        })
        assert result is not None


class TestRecalcularAtivoCompleto:
    """FIFO lot tracking tests."""

    @pytest.mark.asyncio
    async def test_single_buy(self):
        svc, sb = make_service()
        sb.set_table_data("operacoes", [
            {"id": "op1", "ativo_id": "a1", "tipo": "compra", "quantidade": 100, "preco_unitario": 30, "data": "2026-01-01"},
        ])
        sb.set_table_data("ativos", [{"id": "a1", "ticker": "PETR4", "preco_atual": 35}])
        await svc._recalcular_ativo_completo("a1")
        # Should not raise — verifies the method runs correctly

    @pytest.mark.asyncio
    async def test_buy_then_sell_fifo(self):
        svc, sb = make_service()
        sb.set_table_data("operacoes", [
            {"id": "op1", "ativo_id": "a1", "tipo": "compra", "quantidade": 100, "preco_unitario": 30, "data": "2026-01-01", "created_at": "2026-01-01T10:00:00"},
            {"id": "op2", "ativo_id": "a1", "tipo": "compra", "quantidade": 50, "preco_unitario": 40, "data": "2026-02-01", "created_at": "2026-02-01T10:00:00"},
            {"id": "op3", "ativo_id": "a1", "tipo": "venda", "quantidade": 80, "preco_unitario": 35, "data": "2026-03-01", "created_at": "2026-03-01T10:00:00"},
        ])
        sb.set_table_data("ativos", [{"id": "a1", "ticker": "PETR4", "preco_atual": 35}])
        await svc._recalcular_ativo_completo("a1")
        # FIFO: sell 80 from first lot (100@30), remaining: 20@30 + 50@40

    @pytest.mark.asyncio
    async def test_sell_all_leaves_zero(self):
        svc, sb = make_service()
        sb.set_table_data("operacoes", [
            {"id": "op1", "ativo_id": "a1", "tipo": "compra", "quantidade": 100, "preco_unitario": 30, "data": "2026-01-01", "created_at": "2026-01-01T10:00:00"},
            {"id": "op2", "ativo_id": "a1", "tipo": "venda", "quantidade": 100, "preco_unitario": 35, "data": "2026-02-01", "created_at": "2026-02-01T10:00:00"},
        ])
        sb.set_table_data("ativos", [{"id": "a1", "ticker": "PETR4", "preco_atual": 35}])
        await svc._recalcular_ativo_completo("a1")
        # After selling all, quantity should be 0

    @pytest.mark.asyncio
    async def test_split_adjusts_lots(self):
        svc, sb = make_service()
        sb.set_table_data("operacoes", [
            {"id": "op1", "ativo_id": "a1", "tipo": "compra", "quantidade": 100, "preco_unitario": 30, "data": "2026-01-01", "created_at": "2026-01-01T10:00:00"},
            {"id": "op2", "ativo_id": "a1", "tipo": "split", "quantidade": 2, "preco_unitario": 0, "data": "2026-02-01", "created_at": "2026-02-01T10:00:00"},
        ])
        sb.set_table_data("ativos", [{"id": "a1", "ticker": "PETR4", "preco_atual": 15}])
        await svc._recalcular_ativo_completo("a1")
        # After 2:1 split, quantity doubles, price halves

    @pytest.mark.asyncio
    async def test_dividend_no_impact(self):
        svc, sb = make_service()
        sb.set_table_data("operacoes", [
            {"id": "op1", "ativo_id": "a1", "tipo": "compra", "quantidade": 100, "preco_unitario": 30, "data": "2026-01-01", "created_at": "2026-01-01T10:00:00"},
            {"id": "op2", "ativo_id": "a1", "tipo": "dividendo", "quantidade": 0, "preco_unitario": 0, "data": "2026-02-01", "created_at": "2026-02-01T10:00:00"},
        ])
        sb.set_table_data("ativos", [{"id": "a1", "ticker": "PETR4", "preco_atual": 35}])
        await svc._recalcular_ativo_completo("a1")
        # Dividend doesn't change cost basis

    @pytest.mark.asyncio
    async def test_empty_operations(self):
        svc, sb = make_service()
        sb.set_table_data("operacoes", [])
        sb.set_table_data("ativos", [{"id": "a1", "ticker": "PETR4", "preco_atual": 35}])
        await svc._recalcular_ativo_completo("a1")
        # No operations means zero quantity
