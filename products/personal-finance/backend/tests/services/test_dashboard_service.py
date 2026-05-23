"""Unit tests for DashboardService — KPIs and summary aggregation."""
import pytest
from datetime import date, timedelta
from tests.conftest import MockSupabaseClient


ORG_ID = "test-org-123"


def make_service(mock_sb=None):
    from app.services.dashboard_service import DashboardService
    sb = mock_sb or MockSupabaseClient()
    return DashboardService(sb, ORG_ID), sb


class TestKPIs:
    @pytest.mark.asyncio
    async def test_aggregates_patrimonio_and_cash_flow(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [
            {"id": "c1", "org_id": ORG_ID, "nome": "Corrente", "tipo": "corrente", "saldo": 10000, "ativo": True},
        ])
        sb.set_table_data("ativos", [
            {"id": "a1", "org_id": ORG_ID, "ticker": "PETR4", "valor_atual": 5000, "ganho_perda": 500, "carteira_id": "cart1"},
        ])
        sb.set_table_data("resumos_mensais", [])
        sb.set_table_data("transacoes", [
            {"id": "t1", "org_id": ORG_ID, "tipo": "receita", "valor": 8000, "data": f"{date.today().isoformat()}", "categoria": None},
            {"id": "t2", "org_id": ORG_ID, "tipo": "despesa", "valor": 3000, "data": f"{date.today().isoformat()}", "categoria": None},
        ])
        result = await svc.kpis()
        assert result["patrimonio_liquido"] == 15000
        assert result["receita_mensal"] == 8000
        assert result["despesa_mensal"] == 3000
        assert result["fluxo_caixa_mensal"] == 5000
        assert result["retorno_investimentos"] == 500
        assert result["valor_investimentos"] == 5000

    @pytest.mark.asyncio
    async def test_zero_state(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [])
        sb.set_table_data("ativos", [])
        sb.set_table_data("resumos_mensais", [])
        sb.set_table_data("transacoes", [])
        result = await svc.kpis()
        assert result["patrimonio_liquido"] == 0
        assert result["receita_mensal"] == 0
        assert result["despesa_mensal"] == 0
        assert result["retorno_investimentos"] == 0
        assert result["valor_investimentos"] == 0

    @pytest.mark.asyncio
    async def test_investment_return_aggregation(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [])
        sb.set_table_data("ativos", [
            {"id": "a1", "org_id": ORG_ID, "valor_atual": 10000, "ganho_perda": 1500, "carteira_id": "c1"},
            {"id": "a2", "org_id": ORG_ID, "valor_atual": 5000, "ganho_perda": -200, "carteira_id": "c1"},
        ])
        sb.set_table_data("resumos_mensais", [])
        sb.set_table_data("transacoes", [])
        result = await svc.kpis()
        assert result["retorno_investimentos"] == 1300
        assert result["valor_investimentos"] == 15000

    @pytest.mark.asyncio
    async def test_taxa_poupanca(self):
        svc, sb = make_service()
        sb.set_table_data("contas", [])
        sb.set_table_data("ativos", [])
        sb.set_table_data("resumos_mensais", [])
        sb.set_table_data("transacoes", [
            {"id": "t1", "org_id": ORG_ID, "tipo": "receita", "valor": 10000, "data": f"{date.today().isoformat()}", "categoria": None},
            {"id": "t2", "org_id": ORG_ID, "tipo": "despesa", "valor": 6000, "data": f"{date.today().isoformat()}", "categoria": None},
        ])
        result = await svc.kpis()
        assert result["taxa_poupanca"] == 40.0


class TestResumo:
    @pytest.mark.asyncio
    async def test_returns_recent_transactions(self):
        svc, sb = make_service()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        sb.set_table_data("transacoes", [
            {"id": "t1", "org_id": ORG_ID, "descricao": "Compra", "data": yesterday, "valor": 100, "tipo": "despesa"},
        ])
        sb.set_table_data("recorrentes", [])
        sb.set_table_data("metas", [])
        result = await svc.resumo()
        assert len(result["transacoes_recentes"]) == 1
        assert result["transacoes_recentes"][0]["id"] == "t1"

    @pytest.mark.asyncio
    async def test_upcoming_bills(self):
        svc, sb = make_service()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        sb.set_table_data("transacoes", [])
        sb.set_table_data("recorrentes", [
            {"id": "r1", "org_id": ORG_ID, "nome": "Aluguel", "valor": 2000, "proxima_data": tomorrow, "ativo": True},
        ])
        sb.set_table_data("metas", [])
        result = await svc.resumo()
        assert len(result["proximas_contas"]) == 1
        assert result["proximas_contas"][0]["nome"] == "Aluguel"

    @pytest.mark.asyncio
    async def test_goals_with_progress_percentage(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [])
        sb.set_table_data("recorrentes", [])
        sb.set_table_data("metas", [
            {"id": "m1", "org_id": ORG_ID, "nome": "Emergencia", "valor_alvo": 10000, "valor_atual": 4000, "status": "ativa", "prioridade": "alta"},
        ])
        result = await svc.resumo()
        assert len(result["metas_ativas"]) == 1
        assert result["metas_ativas"][0]["percentual"] == 40.0

    @pytest.mark.asyncio
    async def test_empty_state(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [])
        sb.set_table_data("recorrentes", [])
        sb.set_table_data("metas", [])
        result = await svc.resumo()
        assert result["transacoes_recentes"] == []
        assert result["proximas_contas"] == []
        assert result["metas_ativas"] == []
