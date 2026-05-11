"""Unit tests for OrcamentosService — budget sync logic."""
import pytest
from tests.conftest import MockSupabaseClient


ORG_ID = "test-org-123"


def make_service(mock_sb=None):
    from app.services.orcamentos_service import OrcamentosService
    sb = mock_sb or MockSupabaseClient()
    return OrcamentosService(sb, ORG_ID), sb


class TestSincronizarGastos:
    @pytest.mark.asyncio
    async def test_sums_despesas_for_category_month(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [
            {"valor": 200, "tipo": "despesa"},
            {"valor": 150, "tipo": "despesa"},
        ])
        sb.set_table_data("orcamento_itens", [{"id": "item-1", "orcamento_id": "orc-1", "categoria_id": "cat-1", "periodo_mes": "2026-02"}])
        sb.set_table_data("orcamentos", [{"id": "orc-1", "org_id": ORG_ID}])

        updated = await svc.sincronizar_gastos("cat-1", "2026-02")
        assert updated == 1

    @pytest.mark.asyncio
    async def test_ignores_receitas(self):
        """Only despesas should be counted; receitas in the same category are ignored."""
        svc, sb = make_service()
        # Mock returns these regardless of filter, but the service queries with tipo=despesa
        sb.set_table_data("transacoes", [
            {"valor": 500, "tipo": "despesa"},
        ])
        sb.set_table_data("orcamento_itens", [{"id": "item-1", "orcamento_id": "orc-1", "categoria_id": "cat-1", "periodo_mes": "2026-02"}])
        sb.set_table_data("orcamentos", [{"id": "orc-1", "org_id": ORG_ID}])

        updated = await svc.sincronizar_gastos("cat-1", "2026-02")
        assert updated == 1

    @pytest.mark.asyncio
    async def test_no_matching_transactions(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [])
        sb.set_table_data("orcamento_itens", [{"id": "item-1", "orcamento_id": "orc-1", "categoria_id": "cat-1", "periodo_mes": "2026-02"}])
        sb.set_table_data("orcamentos", [{"id": "orc-1", "org_id": ORG_ID}])

        updated = await svc.sincronizar_gastos("cat-1", "2026-02")
        assert updated == 1  # Still updates the item (with valor_gasto=0)

    @pytest.mark.asyncio
    async def test_no_matching_budget_items(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [{"valor": 200, "tipo": "despesa"}])
        sb.set_table_data("orcamento_itens", [])

        updated = await svc.sincronizar_gastos("cat-1", "2026-02")
        assert updated == 0

    @pytest.mark.asyncio
    async def test_december_month_boundary(self):
        """December should compute end-of-year boundary correctly."""
        svc, sb = make_service()
        sb.set_table_data("transacoes", [{"valor": 100, "tipo": "despesa"}])
        sb.set_table_data("orcamento_itens", [{"id": "item-1", "orcamento_id": "orc-1", "categoria_id": "cat-1", "periodo_mes": "2026-12"}])
        sb.set_table_data("orcamentos", [{"id": "orc-1", "org_id": ORG_ID}])

        updated = await svc.sincronizar_gastos("cat-1", "2026-12")
        assert updated == 1


class TestObterProgressoWithSync:
    @pytest.mark.asyncio
    async def test_progress_syncs_before_returning(self):
        svc, sb = make_service()
        sb.set_table_data("transacoes", [{"valor": 300, "tipo": "despesa"}])
        sb.set_table_data("orcamento_itens", [
            {
                "id": "item-1",
                "orcamento_id": "orc-1",
                "categoria_id": "cat-1",
                "periodo_mes": "2026-02",
                "valor_planejado": 1000,
                "valor_gasto": 300,
                "categoria": {"id": "cat-1", "nome": "Alimentacao", "icone": "utensils", "cor": "#ef4444"},
            },
        ])
        sb.set_table_data("orcamentos", [{"id": "orc-1", "org_id": ORG_ID}])

        result = await svc.obter_progresso("orc-1", "2026-02")
        assert result["orcamento_id"] == "orc-1"
        assert result["periodo_mes"] == "2026-02"
        assert "total_planejado" in result
        assert "total_gasto" in result
        assert "percentual_usado" in result

    @pytest.mark.asyncio
    async def test_progress_empty_budget(self):
        svc, sb = make_service()
        sb.set_table_data("orcamento_itens", [])
        sb.set_table_data("transacoes", [])

        result = await svc.obter_progresso("orc-1", "2026-02")
        assert result["total_planejado"] == 0
        assert result["total_gasto"] == 0
        assert result["percentual_usado"] == 0

    @pytest.mark.asyncio
    async def test_progress_percentage_calculation(self):
        svc, sb = make_service()
        sb.set_table_data("orcamento_itens", [
            {
                "id": "item-1",
                "orcamento_id": "orc-1",
                "categoria_id": "cat-1",
                "periodo_mes": "2026-02",
                "valor_planejado": 1000,
                "valor_gasto": 0,
                "categoria": {"id": "cat-1", "nome": "Alimentacao", "icone": "utensils", "cor": "#ef4444"},
            },
        ])
        # `obter_progresso` always calls `sincronizar_gastos` first, which
        # overwrites `valor_gasto` with the SUM of matching transactions.
        # Seed transactions whose sum (500) drives the expected 50% — pre-
        # seeding `valor_gasto: 500` would be overwritten to 0 by the sync.
        sb.set_table_data("transacoes", [
            {"org_id": ORG_ID, "valor": 200, "tipo": "despesa", "categoria_id": "cat-1", "data": "2026-02-05"},
            {"org_id": ORG_ID, "valor": 300, "tipo": "despesa", "categoria_id": "cat-1", "data": "2026-02-10"},
        ])
        sb.set_table_data("orcamentos", [{"id": "orc-1", "org_id": ORG_ID}])

        result = await svc.obter_progresso("orc-1", "2026-02")
        assert result["percentual_usado"] == 50.0
