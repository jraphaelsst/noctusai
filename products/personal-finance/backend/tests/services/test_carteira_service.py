"""Unit tests for CarteiraService — portfolio management and summary."""
import pytest
from tests.conftest import MockSupabaseClient


ORG_ID = "test-org-123"


def make_service(mock_sb=None):
    from app.services.carteira_service import CarteiraService
    sb = mock_sb or MockSupabaseClient()
    return CarteiraService(sb, ORG_ID), sb


SAMPLE_CARTEIRA = {
    "id": "cart-001",
    "org_id": ORG_ID,
    "nome": "Renda Variavel",
    "tipo": "investimento",
    "corretora": "Clear",
    "ativo": True,
    "created_at": "2026-01-01T10:00:00",
}


class TestListar:
    @pytest.mark.asyncio
    async def test_returns_enriched_list(self):
        svc, sb = make_service()
        sb.set_table_data("carteiras", [SAMPLE_CARTEIRA])
        sb.set_table_data("ativos", [
            {"id": "a1", "carteira_id": "cart-001", "valor_atual": 5000, "ganho_perda": 500, "tipo": "acao"},
            {"id": "a2", "carteira_id": "cart-001", "valor_atual": 3000, "ganho_perda": -200, "tipo": "fii"},
        ])
        result = await svc.listar()
        assert len(result) == 1
        assert result[0]["valor_total"] == 8000
        assert result[0]["ganho_perda_total"] == 300
        assert result[0]["total_ativos"] == 2

    @pytest.mark.asyncio
    async def test_empty_portfolio(self):
        svc, sb = make_service()
        sb.set_table_data("carteiras", [SAMPLE_CARTEIRA])
        sb.set_table_data("ativos", [])
        result = await svc.listar()
        assert result[0]["valor_total"] == 0
        assert result[0]["total_ativos"] == 0


class TestCriar:
    @pytest.mark.asyncio
    async def test_creates_carteira(self):
        svc, sb = make_service()
        sb.set_table_data("carteiras", [SAMPLE_CARTEIRA])
        result = await svc.criar({"nome": "Nova", "tipo": "investimento"})
        assert result is not None


class TestResumo:
    @pytest.mark.asyncio
    async def test_allocation_by_type(self):
        svc, sb = make_service()
        sb.set_table_data("carteiras", [SAMPLE_CARTEIRA])
        sb.set_table_data("ativos", [
            {"id": "a1", "carteira_id": "cart-001", "valor_atual": 6000, "ganho_perda": 600, "preco_medio": 27, "quantidade": 200, "tipo": "acao"},
            {"id": "a2", "carteira_id": "cart-001", "valor_atual": 4000, "ganho_perda": -100, "preco_medio": 42, "quantidade": 100, "tipo": "fii"},
        ])
        sb.set_table_data("alocacao_alvo", [])
        result = await svc.resumo("cart-001")
        assert result["valor_total"] == 10000
        assert result["total_ativos"] == 2
        assert len(result["alocacao_atual"]) == 2
        # acao: 60%, fii: 40%
        acao_alloc = next(a for a in result["alocacao_atual"] if a["tipo"] == "acao")
        assert acao_alloc["percentual"] == 60.0

    @pytest.mark.asyncio
    async def test_ganho_perda_pct(self):
        svc, sb = make_service()
        sb.set_table_data("carteiras", [SAMPLE_CARTEIRA])
        sb.set_table_data("ativos", [
            {"id": "a1", "carteira_id": "cart-001", "valor_atual": 11000, "ganho_perda": 1000, "preco_medio": 100, "quantidade": 100, "tipo": "acao"},
        ])
        sb.set_table_data("alocacao_alvo", [])
        result = await svc.resumo("cart-001")
        assert result["ganho_perda_pct"] == 10.0  # (11000/10000 - 1) * 100

    @pytest.mark.asyncio
    async def test_includes_target_allocation(self):
        svc, sb = make_service()
        sb.set_table_data("carteiras", [SAMPLE_CARTEIRA])
        sb.set_table_data("ativos", [])
        sb.set_table_data("alocacao_alvo", [
            {"id": "al1", "carteira_id": "cart-001", "classe_ativo": "acao", "percentual": 60},
            {"id": "al2", "carteira_id": "cart-001", "classe_ativo": "fii", "percentual": 40},
        ])
        result = await svc.resumo("cart-001")
        assert len(result["alocacao_alvo"]) == 2

    @pytest.mark.asyncio
    async def test_nonexistent_carteira(self):
        svc, sb = make_service()
        sb.set_table_data("carteiras", [])
        result = await svc.resumo("cart-999")
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_portfolio_summary(self):
        svc, sb = make_service()
        sb.set_table_data("carteiras", [SAMPLE_CARTEIRA])
        sb.set_table_data("ativos", [])
        sb.set_table_data("alocacao_alvo", [])
        result = await svc.resumo("cart-001")
        assert result["valor_total"] == 0
        assert result["ganho_perda_pct"] == 0
        assert result["alocacao_atual"] == []
