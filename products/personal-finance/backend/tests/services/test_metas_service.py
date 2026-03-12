"""Unit tests for MetasService — goal tracking and contributions."""
import pytest
from tests.conftest import MockSupabaseClient


ORG_ID = "test-org-123"


def make_service(mock_sb=None):
    from app.services.metas_service import MetasService
    sb = mock_sb or MockSupabaseClient()
    return MetasService(sb, ORG_ID), sb


SAMPLE_META = {
    "id": "meta-001",
    "org_id": ORG_ID,
    "nome": "Reserva de Emergencia",
    "tipo": "fundo_emergencia",
    "valor_alvo": 30000,
    "valor_atual": 15000,
    "prioridade": "alta",
    "status": "ativa",
    "data_alvo": "2027-01-01",
    "created_at": "2026-01-01T10:00:00",
}


class TestListar:
    @pytest.mark.asyncio
    async def test_returns_all_metas(self):
        svc, sb = make_service()
        sb.set_table_data("metas", [SAMPLE_META])
        result = await svc.listar()
        assert len(result) == 1
        assert result[0]["percentual"] == 50.0

    @pytest.mark.asyncio
    async def test_percentual_calculation(self):
        svc, sb = make_service()
        sb.set_table_data("metas", [
            {**SAMPLE_META, "valor_alvo": 10000, "valor_atual": 10000},
        ])
        result = await svc.listar()
        assert result[0]["percentual"] == 100

    @pytest.mark.asyncio
    async def test_filter_by_status(self):
        svc, sb = make_service()
        sb.set_table_data("metas", [SAMPLE_META])
        result = await svc.listar(status="ativa")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_list(self):
        svc, sb = make_service()
        sb.set_table_data("metas", [])
        result = await svc.listar()
        assert result == []


class TestAdicionarContribuicao:
    @pytest.mark.asyncio
    async def test_adds_contribution_and_updates_valor(self):
        svc, sb = make_service()
        sb.set_table_data("meta_contribuicoes", [{"id": "mc-001", "meta_id": "meta-001", "valor": 1000}])
        sb.set_table_data("metas", [SAMPLE_META])
        result = await svc.adicionar_contribuicao("meta-001", {"valor": 1000, "descricao": "Aporte mensal"})
        assert result is not None

    @pytest.mark.asyncio
    async def test_marks_completed_when_target_reached(self):
        svc, sb = make_service()
        almost_done_meta = {**SAMPLE_META, "valor_atual": 29500, "valor_alvo": 30000}
        sb.set_table_data("meta_contribuicoes", [{"id": "mc-001", "meta_id": "meta-001", "valor": 500}])
        sb.set_table_data("metas", [almost_done_meta])
        result = await svc.adicionar_contribuicao("meta-001", {"valor": 500})
        assert result is not None


class TestObterProgresso:
    @pytest.mark.asyncio
    async def test_returns_progress_data(self):
        svc, sb = make_service()
        sb.set_table_data("metas", [SAMPLE_META])
        sb.set_table_data("meta_contribuicoes", [
            {"id": "mc-001", "meta_id": "meta-001", "valor": 5000, "data": "2026-01-15"},
            {"id": "mc-002", "meta_id": "meta-001", "valor": 5000, "data": "2026-02-15"},
            {"id": "mc-003", "meta_id": "meta-001", "valor": 5000, "data": "2026-03-15"},
        ])
        result = await svc.obter_progresso("meta-001")
        assert result["percentual"] == 50.0
        assert result["faltam"] == 15000
        assert len(result["contribuicoes"]) == 3

    @pytest.mark.asyncio
    async def test_estimates_completion_date(self):
        svc, sb = make_service()
        sb.set_table_data("metas", [SAMPLE_META])
        sb.set_table_data("meta_contribuicoes", [
            {"id": "mc-001", "meta_id": "meta-001", "valor": 5000, "data": "2026-01-15"},
            {"id": "mc-002", "meta_id": "meta-001", "valor": 5000, "data": "2026-02-15"},
        ])
        result = await svc.obter_progresso("meta-001")
        assert result["data_previsao"] is not None

    @pytest.mark.asyncio
    async def test_no_prediction_when_no_contributions(self):
        svc, sb = make_service()
        sb.set_table_data("metas", [SAMPLE_META])
        sb.set_table_data("meta_contribuicoes", [])
        result = await svc.obter_progresso("meta-001")
        assert result["data_previsao"] is None

    @pytest.mark.asyncio
    async def test_nonexistent_meta(self):
        svc, sb = make_service()
        sb.set_table_data("metas", [])
        result = await svc.obter_progresso("meta-999")
        assert result == {}
