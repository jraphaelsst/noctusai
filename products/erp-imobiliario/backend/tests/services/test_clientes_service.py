"""
Unit tests for ClientesService — client management, search, archiving, pipeline moves.
"""
import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# search_filter
# ---------------------------------------------------------------------------

class TestSearchFilter:

    def test_matches_nome(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient()
        svc = ClientesService(db, "user-1")

        data = [
            {"nome": "João Silva", "email": "joao@test.com"},
            {"nome": "Maria Santos", "email": "maria@test.com"},
        ]

        result = svc.search_filter(data, "João")
        assert len(result) == 1
        assert result[0]["nome"] == "João Silva"

    def test_matches_email(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient()
        svc = ClientesService(db, "user-1")

        data = [
            {"nome": "João", "email": "joao@company.com"},
            {"nome": "Maria", "email": "maria@other.com"},
        ]

        result = svc.search_filter(data, "company")
        assert len(result) == 1
        assert result[0]["nome"] == "João"

    def test_case_insensitive(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient()
        svc = ClientesService(db, "user-1")

        data = [{"nome": "JOÃO SILVA", "email": "j@test.com"}]

        result = svc.search_filter(data, "joão")
        assert len(result) == 1

    def test_matches_telefone(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient()
        svc = ClientesService(db, "user-1")

        data = [
            {"nome": "A", "telefone": "11999990000"},
            {"nome": "B", "telefone": "21888880000"},
        ]

        result = svc.search_filter(data, "999990000")
        assert len(result) == 1
        assert result[0]["nome"] == "A"

    def test_no_match_returns_empty(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient()
        svc = ClientesService(db, "user-1")

        data = [{"nome": "João", "email": "joao@test.com"}]
        result = svc.search_filter(data, "inexistente")
        assert result == []

    def test_empty_data_returns_empty(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient()
        svc = ClientesService(db, "user-1")

        result = svc.search_filter([], "qualquer")
        assert result == []

    def test_matches_observacoes(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient()
        svc = ClientesService(db, "user-1")

        data = [
            {"nome": "A", "observacoes": "Interessado em apartamentos"},
            {"nome": "B", "observacoes": "Quer casa com piscina"},
        ]

        result = svc.search_filter(data, "apartamentos")
        assert len(result) == 1
        assert result[0]["nome"] == "A"


# ---------------------------------------------------------------------------
# validate_etapa
# ---------------------------------------------------------------------------

class TestValidateEtapa:

    def test_valid_etapas(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient()
        svc = ClientesService(db, "user-1")

        for etapa in ["qualificacao", "visitas", "proposta", "negociacao", "fechado"]:
            assert svc.validate_etapa(etapa) is True

    def test_invalid_etapa(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient()
        svc = ClientesService(db, "user-1")

        assert svc.validate_etapa("desconhecida") is False
        assert svc.validate_etapa("") is False


# ---------------------------------------------------------------------------
# get_cliente
# ---------------------------------------------------------------------------

class TestGetCliente:

    @pytest.mark.asyncio
    async def test_returns_client_data(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient(data={"id": "c1", "nome": "João", "email": "j@test.com"})
        svc = ClientesService(db, "user-1")

        result = await svc.get_cliente("c1")

        assert result is not None
        assert result["id"] == "c1"
        assert result["nome"] == "João"

    @pytest.mark.asyncio
    async def test_returns_empty_when_not_found(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient(data=None)
        svc = ClientesService(db, "user-1")

        result = await svc.get_cliente("missing-id")

        # MockSupabaseClient(data=None) yields [] — real Supabase would raise PGRST116
        assert not result


# ---------------------------------------------------------------------------
# create_cliente
# ---------------------------------------------------------------------------

class TestCreateCliente:

    @pytest.mark.asyncio
    async def test_creates_and_returns_client(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient()
        db.set_sequential_responses(
            "clientes",
            [MockSupabaseResponse(data=[{"id": "c-new", "nome": "Maria", "usuario_id": "user-1"}])],
        )
        svc = ClientesService(db, "user-1")

        with patch("app.services.clientes_service.log_action"):
            result = await svc.create_cliente({"nome": "Maria"})

        assert result is not None
        assert result["id"] == "c-new"

    @pytest.mark.asyncio
    async def test_sets_usuario_id(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient()
        svc = ClientesService(db, "user-1")

        data = {"nome": "Test"}
        with patch("app.services.clientes_service.log_action"):
            await svc.create_cliente(data)

        assert data["usuario_id"] == "user-1"


# ---------------------------------------------------------------------------
# update_cliente
# ---------------------------------------------------------------------------

class TestUpdateCliente:

    @pytest.mark.asyncio
    async def test_updates_and_returns_client(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient(data=[{"id": "c1", "nome": "João Atualizado"}])
        svc = ClientesService(db, "user-1")

        with patch("app.services.clientes_service.log_action"):
            result = await svc.update_cliente("c1", {"nome": "João Atualizado"})

        assert result is not None
        assert result["nome"] == "João Atualizado"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient(data=[])
        svc = ClientesService(db, "user-1")

        with patch("app.services.clientes_service.log_action"):
            result = await svc.update_cliente("missing", {"nome": "X"})

        assert result is None


# ---------------------------------------------------------------------------
# delete_cliente
# ---------------------------------------------------------------------------

class TestDeleteCliente:

    @pytest.mark.asyncio
    async def test_returns_true(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient(data=[])
        svc = ClientesService(db, "user-1")

        with patch("app.services.clientes_service.log_action"):
            result = await svc.delete_cliente("c1")

        assert result is True


# ---------------------------------------------------------------------------
# toggle_archive
# ---------------------------------------------------------------------------

class TestToggleArchive:

    @pytest.mark.asyncio
    async def test_archives_when_not_archived(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient()
        # First call (select): returns current state
        # `id` required on seed: production filters by `.eq("id", cliente_id)`
        # then `.single()`. Pre-MOCK-SELECT-PREDICATE-FIX predicates were
        # tracked-but-unevaluated; once SELECT obeys them, missing `id` makes
        # the SELECT 404 and `toggle_archive` returns (None, False).
        db.set_table_data("clientes", {"id": "c1", "arquivado": False, "nome": "João"})

        svc = ClientesService(db, "user-1")

        with patch("app.services.clientes_service.log_action"):
            result, novo_estado = await svc.toggle_archive("c1")

        # The mock always returns the same data for this table,
        # but we verify the toggle logic attempted to flip the state
        assert novo_estado is True

    @pytest.mark.asyncio
    async def test_unarchives_when_archived(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient()
        db.set_table_data("clientes", {"arquivado": True, "nome": "Maria"})

        svc = ClientesService(db, "user-1")

        with patch("app.services.clientes_service.log_action"):
            result, novo_estado = await svc.toggle_archive("c2")

        assert novo_estado is False

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient(data=None)
        svc = ClientesService(db, "user-1")

        result, novo_estado = await svc.toggle_archive("missing")

        assert result is None
        assert novo_estado is False


# ---------------------------------------------------------------------------
# move_etapa
# ---------------------------------------------------------------------------

class TestMoveEtapa:

    @pytest.mark.asyncio
    async def test_moves_to_new_stage(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient(data=[{
            "id": "c1", "nome": "João", "etapa_atual": "visitas"
        }])
        svc = ClientesService(db, "user-1")

        with patch("app.services.clientes_service.log_action"):
            result = await svc.move_etapa("c1", "proposta")

        assert result is not None

    @pytest.mark.asyncio
    async def test_moves_with_kanban_position(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient(data=[{
            "id": "c1", "nome": "João", "etapa_atual": "proposta", "kanban_pos": 2
        }])
        svc = ClientesService(db, "user-1")

        with patch("app.services.clientes_service.log_action"):
            result = await svc.move_etapa("c1", "negociacao", novo_indice=2)

        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        from app.services.clientes_service import ClientesService

        db = MockSupabaseClient(data=[])
        svc = ClientesService(db, "user-1")

        with patch("app.services.clientes_service.log_action"):
            result = await svc.move_etapa("missing", "fechado")

        assert result is None
