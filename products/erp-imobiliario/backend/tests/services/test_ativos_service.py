"""
Unit tests for ativos_service — asset CRUD, search filtering, and label helpers.
"""
import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db_for_insert(inserted_record):
    """Return a MockSupabaseClient where insert chains return *inserted_record*."""
    db = MockSupabaseClient()
    builder = MagicMock()
    builder.insert = MagicMock(return_value=builder)
    builder.select = MagicMock(return_value=builder)
    builder.single = MagicMock(return_value=builder)
    builder.eq = MagicMock(return_value=builder)
    builder.execute = MagicMock(return_value=MockSupabaseResponse(data=[inserted_record]))
    return db, builder


# ---------------------------------------------------------------------------
# search_filter
# ---------------------------------------------------------------------------

class TestSearchFilter:

    def test_search_by_cidade(self):
        from app.services.ativos_service import AtivosService
        db = MockSupabaseClient()
        svc = AtivosService(db, "u-1")

        data = [
            {"id": "a-1", "cidade": "Sao Paulo", "bairro": "Centro"},
            {"id": "a-2", "cidade": "Rio de Janeiro", "bairro": "Copacabana"},
        ]

        result = svc.search_filter(data, "sao paulo")

        assert len(result) == 1
        assert result[0]["id"] == "a-1"

    def test_search_by_bairro(self):
        from app.services.ativos_service import AtivosService
        db = MockSupabaseClient()
        svc = AtivosService(db, "u-1")

        data = [
            {"id": "a-1", "bairro": "Centro"},
            {"id": "a-2", "bairro": "Copacabana"},
        ]

        result = svc.search_filter(data, "copacabana")

        assert len(result) == 1
        assert result[0]["id"] == "a-2"

    def test_search_case_insensitive(self):
        from app.services.ativos_service import AtivosService
        db = MockSupabaseClient()
        svc = AtivosService(db, "u-1")

        data = [{"id": "a-1", "titulo_anuncio": "Apartamento Luxo"}]

        result = svc.search_filter(data, "APARTAMENTO")

        assert len(result) == 1

    def test_search_no_match(self):
        from app.services.ativos_service import AtivosService
        db = MockSupabaseClient()
        svc = AtivosService(db, "u-1")

        data = [{"id": "a-1", "cidade": "Sao Paulo"}]

        result = svc.search_filter(data, "curitiba")

        assert len(result) == 0

    def test_search_by_id(self):
        from app.services.ativos_service import AtivosService
        db = MockSupabaseClient()
        svc = AtivosService(db, "u-1")

        data = [
            {"id": "abc-123", "cidade": "SP"},
            {"id": "def-456", "cidade": "RJ"},
        ]

        result = svc.search_filter(data, "abc-123")

        assert len(result) == 1
        assert result[0]["id"] == "abc-123"

    def test_search_by_tipo_imovel(self):
        from app.services.ativos_service import AtivosService
        db = MockSupabaseClient()
        svc = AtivosService(db, "u-1")

        data = [
            {"id": "a-1", "tipo_imovel": "apartamento"},
            {"id": "a-2", "tipo_imovel": "casa"},
        ]

        result = svc.search_filter(data, "casa")

        assert len(result) == 1
        assert result[0]["id"] == "a-2"

    def test_search_handles_none_values(self):
        from app.services.ativos_service import AtivosService
        db = MockSupabaseClient()
        svc = AtivosService(db, "u-1")

        data = [{"id": "a-1", "cidade": None, "bairro": None, "titulo_anuncio": "Sala Comercial"}]

        result = svc.search_filter(data, "sala")

        assert len(result) == 1


# ---------------------------------------------------------------------------
# get_ativo
# ---------------------------------------------------------------------------

class TestGetAtivo:

    @pytest.mark.asyncio
    async def test_get_existing_ativo(self):
        ativo = {"id": "a-1", "titulo_anuncio": "Apto Centro", "natureza": "imovel"}
        db = MockSupabaseClient(data=[ativo])

        from app.services.ativos_service import AtivosService
        svc = AtivosService(db, "u-1")

        result = await svc.get_ativo("a-1")

        assert result is not None
        assert result["id"] == "a-1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_ativo(self):
        db = MockSupabaseClient(data=None)

        from app.services.ativos_service import AtivosService
        svc = AtivosService(db, "u-1")

        result = await svc.get_ativo("does-not-exist")

        # MockSupabaseResponse normalises None → [], so result.data is []
        assert not result


# ---------------------------------------------------------------------------
# get_natureza_label
# ---------------------------------------------------------------------------

class TestGetNaturezaLabel:

    def test_imovel_label(self):
        from app.services.ativos_service import AtivosService

        assert AtivosService.get_natureza_label("imovel") == "Imóvel"

    def test_permuta_imovel_label(self):
        from app.services.ativos_service import AtivosService

        assert AtivosService.get_natureza_label("permuta_imovel") == "Permuta de Imóvel"

    def test_permuta_automovel_label(self):
        from app.services.ativos_service import AtivosService

        assert AtivosService.get_natureza_label("permuta_automovel") == "Permuta de Automóvel"

    def test_unknown_natureza_returns_as_is(self):
        from app.services.ativos_service import AtivosService

        assert AtivosService.get_natureza_label("terreno") == "terreno"


# ---------------------------------------------------------------------------
# VALID_NATUREZAS constant
# ---------------------------------------------------------------------------

class TestValidNaturezas:

    def test_expected_naturezas(self):
        from app.services.ativos_service import AtivosService

        assert AtivosService.VALID_NATUREZAS == {"imovel", "permuta_imovel", "permuta_automovel"}
