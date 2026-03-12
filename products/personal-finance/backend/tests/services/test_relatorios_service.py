"""Unit tests for RelatoriosService — monthly reports, cache layer, annual aggregation."""
import pytest
from tests.conftest import MockSupabaseClient


ORG_ID = "test-org-123"


def make_service(mock_sb=None):
    from app.services.relatorios_service import RelatoriosService
    sb = mock_sb or MockSupabaseClient()
    return RelatoriosService(sb, ORG_ID), sb


class TestRelatorioMensal:
    @pytest.mark.asyncio
    async def test_computes_totals(self):
        svc, sb = make_service()
        sb.set_table_data("resumos_mensais", [])  # no cache
        sb.set_table_data("transacoes", [
            {"id": "t1", "tipo": "receita", "valor": 5000, "data": "2026-03-10", "categoria": {"id": "c1", "nome": "Salario", "icone": "", "cor": ""}},
            {"id": "t2", "tipo": "despesa", "valor": 1500, "data": "2026-03-15", "categoria": {"id": "c2", "nome": "Moradia", "icone": "", "cor": ""}},
            {"id": "t3", "tipo": "despesa", "valor": 800, "data": "2026-03-20", "categoria": {"id": "c3", "nome": "Alimentacao", "icone": "", "cor": ""}},
        ])
        result = await svc.relatorio_mensal("2026-03")
        assert result["receita_total"] == 5000
        assert result["despesa_total"] == 2300
        assert result["fluxo_liquido"] == 2700
        assert result["total_transacoes"] == 3

    @pytest.mark.asyncio
    async def test_returns_cache_when_available(self):
        svc, sb = make_service()
        cached_report = {
            "mes": "2026-02",
            "receita_total": 4000,
            "despesa_total": 2000,
            "fluxo_liquido": 2000,
            "taxa_poupanca": 50,
            "total_transacoes": 5,
            "top_categorias": [],
        }
        sb.set_table_data("resumos_mensais", [{"org_id": ORG_ID, "mes": "2026-02", "dados": cached_report}])
        result = await svc.relatorio_mensal("2026-02")
        assert result["receita_total"] == 4000

    @pytest.mark.asyncio
    async def test_empty_month(self):
        svc, sb = make_service()
        sb.set_table_data("resumos_mensais", [])
        sb.set_table_data("transacoes", [])
        result = await svc.relatorio_mensal("2026-01")
        assert result["receita_total"] == 0
        assert result["despesa_total"] == 0
        assert result["total_transacoes"] == 0

    @pytest.mark.asyncio
    async def test_taxa_poupanca(self):
        svc, sb = make_service()
        sb.set_table_data("resumos_mensais", [])
        sb.set_table_data("transacoes", [
            {"id": "t1", "tipo": "receita", "valor": 10000, "data": "2026-03-01", "categoria": None},
            {"id": "t2", "tipo": "despesa", "valor": 6000, "data": "2026-03-15", "categoria": None},
        ])
        result = await svc.relatorio_mensal("2026-03")
        assert result["taxa_poupanca"] == 40.0

    @pytest.mark.asyncio
    async def test_top_categorias_sorted_by_spending(self):
        svc, sb = make_service()
        sb.set_table_data("resumos_mensais", [])
        sb.set_table_data("transacoes", [
            {"id": "t1", "tipo": "despesa", "valor": 500, "data": "2026-03-01", "categoria": {"id": "c1", "nome": "Alimentacao", "icone": "", "cor": ""}},
            {"id": "t2", "tipo": "despesa", "valor": 2000, "data": "2026-03-05", "categoria": {"id": "c2", "nome": "Moradia", "icone": "", "cor": ""}},
            {"id": "t3", "tipo": "despesa", "valor": 300, "data": "2026-03-10", "categoria": {"id": "c1", "nome": "Alimentacao", "icone": "", "cor": ""}},
        ])
        result = await svc.relatorio_mensal("2026-03")
        cats = result["top_categorias"]
        assert len(cats) == 2
        assert cats[0]["nome"] == "Moradia"
        assert cats[0]["total"] == 2000


class TestRelatorioAnual:
    @pytest.mark.asyncio
    async def test_aggregates_twelve_months(self):
        svc, sb = make_service()
        sb.set_table_data("resumos_mensais", [])
        sb.set_table_data("transacoes", [
            {"id": "t1", "tipo": "receita", "valor": 5000, "data": "2026-01-10", "categoria": None},
            {"id": "t2", "tipo": "despesa", "valor": 3000, "data": "2026-01-15", "categoria": None},
        ])
        result = await svc.relatorio_anual("2026")
        assert result["ano"] == "2026"
        assert len(result["meses"]) == 12
        assert result["receita_anual"] >= 5000

    @pytest.mark.asyncio
    async def test_uses_cached_months(self):
        svc, sb = make_service()
        cached = {
            "mes": "2026-01",
            "receita_total": 8000,
            "despesa_total": 4000,
            "fluxo_liquido": 4000,
            "taxa_poupanca": 50,
            "total_transacoes": 10,
            "top_categorias": [],
        }
        sb.set_table_data("resumos_mensais", [{"org_id": ORG_ID, "mes": "2026-01", "dados": cached}])
        sb.set_table_data("transacoes", [])
        result = await svc.relatorio_anual("2026")
        # January should use cached data
        assert result["meses"][0]["receita_total"] == 8000


class TestFluxoCaixa:
    @pytest.mark.asyncio
    async def test_daily_aggregation(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [
            {"id": "t1", "tipo": "receita", "valor": 5000, "data": "2026-03-01"},
            {"id": "t2", "tipo": "despesa", "valor": 200, "data": "2026-03-01"},
            {"id": "t3", "tipo": "despesa", "valor": 800, "data": "2026-03-02"},
        ])
        result = await svc.fluxo_caixa("2026-03-01", "2026-03-31")
        assert len(result["fluxo"]) == 2
        day1 = result["fluxo"][0]
        assert day1["receitas"] == 5000
        assert day1["despesas"] == 200
        assert day1["liquido"] == 4800

    @pytest.mark.asyncio
    async def test_empty_range(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [])
        result = await svc.fluxo_caixa("2026-03-01", "2026-03-31")
        assert result["fluxo"] == []


class TestCacheOperations:
    @pytest.mark.asyncio
    async def test_atualizar_resumo_mensal(self):
        svc, sb = make_service()
        sb.set_table_data("resumos_mensais", [])
        sb.set_table_data("transacoes", [
            {"id": "t1", "tipo": "receita", "valor": 5000, "data": "2026-03-01", "categoria": None},
        ])
        result = await svc.atualizar_resumo_mensal("2026-03")
        assert result["receita_total"] == 5000

    def test_buscar_cache_miss(self):
        svc, sb = make_service()
        sb.set_table_data("resumos_mensais", [])
        result = svc._buscar_cache("2026-03")
        assert result is None

    def test_buscar_cache_hit(self):
        svc, sb = make_service()
        cached = {"mes": "2026-03", "receita_total": 5000, "despesa_total": 2000}
        sb.set_table_data("resumos_mensais", [{"org_id": ORG_ID, "mes": "2026-03", "dados": cached}])
        result = svc._buscar_cache("2026-03")
        assert result is not None
        assert result["receita_total"] == 5000

    def test_buscar_cache_handles_json_string(self):
        import json
        svc, sb = make_service()
        cached = {"mes": "2026-03", "receita_total": 3000}
        sb.set_table_data("resumos_mensais", [{"org_id": ORG_ID, "mes": "2026-03", "dados": json.dumps(cached)}])
        result = svc._buscar_cache("2026-03")
        assert result is not None
        assert result["receita_total"] == 3000
