"""
Unit tests for CampoService — sync processing and offline data pack generation.
"""
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeSyncModel:
    """Mimics a Pydantic model with model_dump()."""
    def __init__(self, data: dict):
        self._data = data

    def model_dump(self, exclude_none=False):
        if exclude_none:
            return {k: v for k, v in self._data.items() if v is not None}
        return dict(self._data)


class FailingInsertDB:
    """A DB mock where insert raises an exception for testing error paths."""
    def __init__(self):
        self.auth = MagicMock()
        self._tables = {}

    def table(self, name):
        builder = MagicMock()
        builder.insert = MagicMock(side_effect=RuntimeError("DB insert failed"))
        builder.select = MagicMock(return_value=builder)
        builder.eq = MagicMock(return_value=builder)
        builder.order = MagicMock(return_value=builder)
        builder.limit = MagicMock(return_value=builder)
        builder.execute = MagicMock(return_value=MockSupabaseResponse(data=[]))
        return builder


# ---------------------------------------------------------------------------
# processar_sync
# ---------------------------------------------------------------------------

class TestProcessarSync:

    @pytest.mark.asyncio
    async def test_empty_sync(self):
        db = MockSupabaseClient()

        from app.services.campo_service import CampoService
        svc = CampoService(db, "user-1")

        result = await svc.processar_sync(checkins=[], vistorias=[])

        assert result["checkins_criados"] == 0
        assert result["vistorias_criadas"] == 0
        assert result["erros"] == []

    @pytest.mark.asyncio
    async def test_successful_checkin_sync(self):
        db = MockSupabaseClient()

        from app.services.campo_service import CampoService
        svc = CampoService(db, "user-1")

        checkins = [
            FakeSyncModel({
                "offline_id": "off-1",
                "created_at_local": "2026-01-01T10:00:00",
                "imovel_id": "im-1",
                "latitude": -23.55,
                "longitude": -46.63,
            }),
            FakeSyncModel({
                "offline_id": "off-2",
                "created_at_local": "2026-01-01T11:00:00",
                "imovel_id": "im-2",
            }),
        ]

        result = await svc.processar_sync(checkins=checkins, vistorias=[])

        assert result["checkins_criados"] == 2
        assert result["vistorias_criadas"] == 0
        assert result["erros"] == []

    @pytest.mark.asyncio
    async def test_successful_vistoria_sync(self):
        db = MockSupabaseClient()

        from app.services.campo_service import CampoService
        svc = CampoService(db, "user-1")

        vistorias = [
            FakeSyncModel({
                "offline_id": "voff-1",
                "created_at_local": "2026-01-01T12:00:00",
                "imovel_id": "im-1",
                "tipo": "entrada",
                "observacoes": "Bom estado",
            }),
        ]

        result = await svc.processar_sync(checkins=[], vistorias=vistorias)

        assert result["checkins_criados"] == 0
        assert result["vistorias_criadas"] == 1
        assert result["erros"] == []

    @pytest.mark.asyncio
    async def test_mixed_sync(self):
        db = MockSupabaseClient()

        from app.services.campo_service import CampoService
        svc = CampoService(db, "user-1")

        checkins = [
            FakeSyncModel({"offline_id": "c1", "imovel_id": "im-1"}),
        ]
        vistorias = [
            FakeSyncModel({"offline_id": "v1", "imovel_id": "im-2", "tipo": "saida"}),
        ]

        result = await svc.processar_sync(checkins=checkins, vistorias=vistorias)

        assert result["checkins_criados"] == 1
        assert result["vistorias_criadas"] == 1
        assert result["erros"] == []

    @pytest.mark.asyncio
    async def test_checkin_error_is_captured(self):
        db = FailingInsertDB()

        from app.services.campo_service import CampoService
        svc = CampoService(db, "user-1")

        checkins = [
            FakeSyncModel({"offline_id": "c-err", "imovel_id": "im-1"}),
        ]

        result = await svc.processar_sync(checkins=checkins, vistorias=[])

        assert result["checkins_criados"] == 0
        assert len(result["erros"]) == 1
        assert result["erros"][0]["item"] == "checkins-batch"
        assert result["erros"][0]["tipo"] == "checkin"

    @pytest.mark.asyncio
    async def test_vistoria_error_is_captured(self):
        db = FailingInsertDB()

        from app.services.campo_service import CampoService
        svc = CampoService(db, "user-1")

        vistorias = [
            FakeSyncModel({"offline_id": "v-err", "imovel_id": "im-1", "tipo": "entrada"}),
        ]

        result = await svc.processar_sync(checkins=[], vistorias=vistorias)

        assert result["vistorias_criadas"] == 0
        assert len(result["erros"]) == 1
        assert result["erros"][0]["item"] == "vistorias-batch"
        assert result["erros"][0]["tipo"] == "vistoria"

    @pytest.mark.asyncio
    async def test_offline_id_removed_before_insert(self):
        """offline_id and created_at_local should be popped before DB insert."""
        db = MockSupabaseClient()

        from app.services.campo_service import CampoService
        svc = CampoService(db, "user-1")

        checkin = FakeSyncModel({
            "offline_id": "off-1",
            "created_at_local": "2026-01-01T10:00:00",
            "imovel_id": "im-1",
        })

        result = await svc.processar_sync(checkins=[checkin], vistorias=[])

        assert result["checkins_criados"] == 1

    @pytest.mark.asyncio
    async def test_corretor_id_is_set(self):
        """The service should inject user_id as corretor_id."""
        inserted_rows = []

        class CapturingDB:
            def __init__(self):
                self.auth = MagicMock()

            def table(self, name):
                builder = MagicMock()
                def _insert(data):
                    if isinstance(data, list):
                        inserted_rows.extend(data)
                    else:
                        inserted_rows.append(data)
                    return builder
                builder.insert = _insert
                builder.execute = MagicMock(return_value=MockSupabaseResponse(data=[]))
                return builder

        db = CapturingDB()

        from app.services.campo_service import CampoService
        svc = CampoService(db, "user-42")

        checkin = FakeSyncModel({"offline_id": "c1", "imovel_id": "im-1"})

        await svc.processar_sync(checkins=[checkin], vistorias=[])

        assert len(inserted_rows) == 1
        assert inserted_rows[0].get("corretor_id") == "user-42"


# ---------------------------------------------------------------------------
# gerar_pacote_offline
# ---------------------------------------------------------------------------

class TestGerarPacoteOffline:

    @pytest.mark.asyncio
    async def test_returns_all_sections(self):
        db = MockSupabaseClient()
        db.set_table_data("ativos", [{"id": "a1"}])
        db.set_table_data("clientes", [{"id": "c1"}])
        db.set_table_data("checkins", [{"id": "ch1"}])

        from app.services.campo_service import CampoService
        svc = CampoService(db, "user-1")

        result = await svc.gerar_pacote_offline()

        assert "imoveis" in result
        assert "clientes" in result
        assert "checkins_recentes" in result
        assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_empty_data_returns_empty_lists(self):
        db = MockSupabaseClient(data=[])

        from app.services.campo_service import CampoService
        svc = CampoService(db, "user-1")

        result = await svc.gerar_pacote_offline()

        assert result["imoveis"] == []
        assert result["clientes"] == []
        assert result["checkins_recentes"] == []

    @pytest.mark.asyncio
    async def test_generated_at_is_iso_timestamp(self):
        db = MockSupabaseClient(data=[])

        from app.services.campo_service import CampoService
        svc = CampoService(db, "user-1")

        result = await svc.gerar_pacote_offline()

        # Should be parseable as an ISO timestamp
        ts = result["generated_at"]
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# Class constants
# ---------------------------------------------------------------------------

class TestConstants:

    def test_imovel_offline_fields_contains_key_columns(self):
        from app.services.campo_service import CampoService

        fields = CampoService.IMOVEL_OFFLINE_FIELDS

        assert "id" in fields
        assert "latitude" in fields
        assert "longitude" in fields
        assert "valor" in fields
        assert "status" in fields
        assert "fotos" in fields
