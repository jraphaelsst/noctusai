"""Unit tests for CategoriasService — hierarchy and CRUD."""
import pytest
from tests.conftest import MockSupabaseClient


ORG_ID = "test-org-123"


def make_service(mock_sb=None):
    from app.services.categorias_service import CategoriasService
    sb = mock_sb or MockSupabaseClient()
    return CategoriasService(sb, ORG_ID), sb


SAMPLE_CAT = {
    "id": "cat-001",
    "org_id": ORG_ID,
    "nome": "Alimentacao",
    "tipo": "despesa",
    "icone": "utensils",
    "cor": "#ef4444",
    "ordem": 1,
    "categoria_pai_id": None,
    "is_sistema": False,
}


class TestListar:
    @pytest.mark.asyncio
    async def test_returns_all_categories(self):
        svc, sb = make_service()
        sb.set_table_data("categorias", [SAMPLE_CAT, {**SAMPLE_CAT, "id": "cat-002", "nome": "Transporte"}])
        result = await svc.listar()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filter_by_tipo(self):
        svc, sb = make_service()
        sb.set_table_data("categorias", [SAMPLE_CAT])
        result = await svc.listar(tipo="despesa")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_list(self):
        svc, sb = make_service()
        sb.set_table_data("categorias", [])
        result = await svc.listar()
        assert result == []


class TestObter:
    @pytest.mark.asyncio
    async def test_returns_single(self):
        svc, sb = make_service()
        sb.set_table_data("categorias", [SAMPLE_CAT])
        result = await svc.obter("cat-001")
        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_empty_when_missing(self):
        svc, sb = make_service()
        sb.set_table_data("categorias", [])
        result = await svc.obter("cat-999")
        assert not result  # empty list from mock .single() on empty data


class TestCriar:
    @pytest.mark.asyncio
    async def test_creates_category(self):
        svc, sb = make_service()
        sb.set_table_data("categorias", [SAMPLE_CAT])
        result = await svc.criar({"nome": "Saude", "tipo": "despesa"})
        assert result is not None

    @pytest.mark.asyncio
    async def test_sets_org_id_and_is_sistema(self):
        svc, sb = make_service()
        sb.set_table_data("categorias", [SAMPLE_CAT])
        data = {"nome": "Lazer", "tipo": "despesa"}
        await svc.criar(data)
        assert data["org_id"] == ORG_ID
        assert data["is_sistema"] is False


class TestAtualizar:
    @pytest.mark.asyncio
    async def test_updates_category(self):
        svc, sb = make_service()
        sb.set_table_data("categorias", [SAMPLE_CAT])
        result = await svc.atualizar("cat-001", {"nome": "Alimentacao e Bebidas"})
        assert result is not None


class TestExcluir:
    @pytest.mark.asyncio
    async def test_deletes_category(self):
        svc, sb = make_service()
        sb.set_table_data("categorias", [SAMPLE_CAT])
        result = await svc.excluir("cat-001")
        assert result is True


class TestArvore:
    @pytest.mark.asyncio
    async def test_builds_tree_from_flat(self):
        svc, sb = make_service()
        parent = SAMPLE_CAT
        child = {
            "id": "cat-002",
            "org_id": ORG_ID,
            "nome": "Restaurantes",
            "tipo": "despesa",
            "icone": "pizza",
            "cor": "#ef4444",
            "ordem": 2,
            "categoria_pai_id": "cat-001",
            "is_sistema": False,
        }
        sb.set_table_data("categorias", [parent, child])
        result = await svc.arvore()
        # Parent should have child in subcategorias
        assert len(result) == 1
        assert result[0]["id"] == "cat-001"
        assert len(result[0]["subcategorias"]) == 1
        assert result[0]["subcategorias"][0]["id"] == "cat-002"

    @pytest.mark.asyncio
    async def test_tree_with_no_children(self):
        svc, sb = make_service()
        sb.set_table_data("categorias", [SAMPLE_CAT])
        result = await svc.arvore()
        assert len(result) == 1
        assert result[0]["subcategorias"] == []

    @pytest.mark.asyncio
    async def test_tree_empty(self):
        svc, sb = make_service()
        sb.set_table_data("categorias", [])
        result = await svc.arvore()
        assert result == []

    @pytest.mark.asyncio
    async def test_tree_filter_by_tipo(self):
        svc, sb = make_service()
        sb.set_table_data("categorias", [SAMPLE_CAT])
        result = await svc.arvore(tipo="despesa")
        assert isinstance(result, list)
