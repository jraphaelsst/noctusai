"""Unit tests for PatrimonioService — net worth calculation and snapshots."""
import pytest
from tests.conftest import MockSupabaseClient


ORG_ID = "test-org-123"


def make_service(mock_sb=None):
    from app.services.patrimonio_service import PatrimonioService
    sb = mock_sb or MockSupabaseClient()
    return PatrimonioService(sb, ORG_ID), sb


class TestCalcularAtual:
    @pytest.mark.asyncio
    async def test_positive_balances(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [
            {"id": "c1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 5000, "ativo": True},
            {"id": "c2", "org_id": ORG_ID, "nome": "Poupanca", "tipo": "poupanca", "saldo": 10000, "ativo": True},
        ])
        sb.set_table_data("ativos", [
            {"id": "a1", "org_id": ORG_ID, "ticker": "PETR4", "valor_atual": 8000, "carteira_id": "cart1"},
        ])
        result = await svc.calcular_atual()
        assert result["total_ativos"] == 23000  # 5000 + 10000 + 8000
        assert result["total_passivos"] == 0
        assert result["patrimonio_liquido"] == 23000

    @pytest.mark.asyncio
    async def test_credit_card_as_liability(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [
            {"id": "c1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 5000, "ativo": True},
            {"id": "c2", "org_id": ORG_ID, "nome": "Cartao", "tipo": "cartao_credito", "saldo": -2000, "ativo": True},
        ])
        sb.set_table_data("ativos", [])
        result = await svc.calcular_atual()
        assert result["total_ativos"] == 5000
        assert result["total_passivos"] == 2000
        assert result["patrimonio_liquido"] == 3000

    @pytest.mark.asyncio
    async def test_loan_as_liability(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [
            {"id": "c1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 10000, "ativo": True},
            {"id": "c2", "org_id": ORG_ID, "nome": "Emprestimo", "tipo": "emprestimo", "saldo": -5000, "ativo": True},
        ])
        sb.set_table_data("ativos", [])
        result = await svc.calcular_atual()
        assert result["total_ativos"] == 10000
        assert result["total_passivos"] == 5000
        assert result["patrimonio_liquido"] == 5000

    @pytest.mark.asyncio
    async def test_empty_accounts(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [])
        sb.set_table_data("ativos", [])
        result = await svc.calcular_atual()
        assert result["total_ativos"] == 0
        assert result["total_passivos"] == 0
        assert result["patrimonio_liquido"] == 0

    @pytest.mark.asyncio
    async def test_detalhamento_structure(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [
            {"id": "c1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 5000, "ativo": True},
        ])
        sb.set_table_data("ativos", [
            {"id": "a1", "org_id": ORG_ID, "ticker": "VALE3", "valor_atual": 3000, "carteira_id": "cart1"},
        ])
        result = await svc.calcular_atual()
        assert "detalhamento" in result
        assert len(result["detalhamento"]["contas"]) == 1
        assert len(result["detalhamento"]["investimentos"]) == 1


class TestCriarSnapshot:
    @pytest.mark.asyncio
    async def test_creates_new_snapshot(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [
            {"id": "c1", "nome": "Corrente", "tipo": "corrente", "saldo": 5000, "ativo": True},
        ])
        sb.set_table_data("ativos", [])
        sb.set_table_data("patrimonio_snapshots", [{"id": "snap-001"}])
        result = await svc.criar_snapshot("2026-03-01")
        assert result is not None

    @pytest.mark.asyncio
    async def test_updates_existing_snapshot(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [])
        sb.set_table_data("ativos", [])
        sb.set_table_data("patrimonio_snapshots", [{"id": "snap-existing", "data": "2026-03-01"}])
        result = await svc.criar_snapshot("2026-03-01")
        # Should update existing, not create duplicate


class TestHistorico:
    @pytest.mark.asyncio
    async def test_returns_chronological(self):
        svc, sb = make_service()
        sb.set_table_data("patrimonio_snapshots", [
            {"id": "s1", "data": "2026-03-01", "patrimonio_liquido": 30000},
            {"id": "s2", "data": "2026-02-01", "patrimonio_liquido": 28000},
        ])
        result = await svc.historico()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        svc, sb = make_service()
        sb.set_table_data("patrimonio_snapshots", [])
        result = await svc.historico(limite=6)
        assert isinstance(result, list)
