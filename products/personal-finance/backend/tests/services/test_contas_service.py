"""Unit tests for ContasService — accounts CRUD and balance queries."""
import pytest
from tests.conftest import MockSupabaseClient


ORG_ID = "test-org-123"


def make_service(mock_sb=None):
    from app.services.contas_service import ContasService
    sb = mock_sb or MockSupabaseClient()
    return ContasService(sb, ORG_ID), sb


SAMPLE_CONTA = {
    "id": "conta-001",
    "org_id": ORG_ID,
    "nome": "Conta Corrente",
    "tipo": "corrente",
    "instituicao": "Itau",
    "saldo": 5000.00,
    "moeda": "BRL",
    "cor": "#3b82f6",
    "icone": "building-2",
    "ativo": True,
    "created_at": "2026-01-01T10:00:00",
}


class TestListar:
    @pytest.mark.asyncio
    async def test_returns_all_accounts(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [
            SAMPLE_CONTA,
            {**SAMPLE_CONTA, "id": "conta-002", "nome": "Poupanca", "tipo": "poupanca"},
        ])
        result = await svc.listar()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filter_by_ativo(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [SAMPLE_CONTA])
        result = await svc.listar(ativo=True)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_filter_inactive(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [])
        result = await svc.listar(ativo=False)
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_list(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [])
        result = await svc.listar()
        assert result == []


class TestObter:
    @pytest.mark.asyncio
    async def test_returns_single(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [SAMPLE_CONTA])
        result = await svc.obter("conta-001")
        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_empty_when_missing(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [])
        result = await svc.obter("conta-999")
        assert not result  # empty list from mock .single() on empty data


class TestCriar:
    @pytest.mark.asyncio
    async def test_creates_account(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [SAMPLE_CONTA])
        result = await svc.criar({"nome": "Nova Conta", "tipo": "corrente", "saldo": 0})
        assert result is not None

    @pytest.mark.asyncio
    async def test_sets_org_id(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [SAMPLE_CONTA])
        data = {"nome": "Carteira", "tipo": "carteira"}
        await svc.criar(data)
        assert data["org_id"] == ORG_ID


class TestAtualizar:
    @pytest.mark.asyncio
    async def test_updates_account(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [SAMPLE_CONTA])
        result = await svc.atualizar("conta-001", {"nome": "Conta Principal"})
        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [])
        result = await svc.atualizar("conta-999", {"nome": "X"})
        assert result is None


class TestExcluir:
    @pytest.mark.asyncio
    async def test_deletes_account(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [SAMPLE_CONTA])
        result = await svc.excluir("conta-001")
        assert result is True


class TestObterSaldos:
    @pytest.mark.asyncio
    async def test_returns_active_balances(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [
            SAMPLE_CONTA,
            {**SAMPLE_CONTA, "id": "conta-002", "nome": "Poupanca", "saldo": 10000, "ativo": True},
        ])
        result = await svc.obter_saldos()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_balances(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [])
        result = await svc.obter_saldos()
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_expected_fields(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [SAMPLE_CONTA])
        result = await svc.obter_saldos()
        assert isinstance(result, list)
        # The mock returns the full data; verify it's a list of dicts
        if result:
            assert "saldo" in result[0]
