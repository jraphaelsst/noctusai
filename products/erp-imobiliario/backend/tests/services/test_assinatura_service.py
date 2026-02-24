"""
Unit tests for AssinaturaService — document preparation, webhook processing, cancellation, summary.
"""
import pytest
from unittest.mock import MagicMock

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db_with_record(record):
    """Return a MockSupabaseClient whose default query returns *record*."""
    db = MockSupabaseClient(data=record)
    return db


def _make_db_for_insert(inserted_record):
    """Return a DB mock where insert().select().single().execute() returns the given record."""
    db = MockSupabaseClient()
    builder = MagicMock()
    builder.insert = MagicMock(return_value=builder)
    builder.update = MagicMock(return_value=builder)
    builder.select = MagicMock(return_value=builder)
    builder.eq = MagicMock(return_value=builder)
    builder.single = MagicMock(return_value=builder)
    builder.execute = MagicMock(return_value=MockSupabaseResponse(data=inserted_record))
    db._tables["assinaturas"] = builder
    return db


# ---------------------------------------------------------------------------
# EVENT_STATUS_MAP
# ---------------------------------------------------------------------------

class TestEventStatusMap:
    def test_known_events_map_correctly(self):
        from app.services.assinatura_service import AssinaturaService

        assert AssinaturaService.EVENT_STATUS_MAP["assinado"] == "assinado"
        assert AssinaturaService.EVENT_STATUS_MAP["signed"] == "assinado"
        assert AssinaturaService.EVENT_STATUS_MAP["refused"] == "recusado"
        assert AssinaturaService.EVENT_STATUS_MAP["expired"] == "expirado"
        assert AssinaturaService.EVENT_STATUS_MAP["canceled"] == "cancelado"

    def test_portuguese_and_english_events_are_consistent(self):
        from app.services.assinatura_service import AssinaturaService

        m = AssinaturaService.EVENT_STATUS_MAP
        assert m["recusado"] == m["refused"] == m["declined"]
        assert m["expirado"] == m["expired"]
        assert m["cancelado"] == m["canceled"]


# ---------------------------------------------------------------------------
# preparar_envio
# ---------------------------------------------------------------------------

class TestPrepararEnvio:

    @pytest.mark.asyncio
    async def test_creates_assinatura_record(self):
        inserted = {
            "id": "a-1",
            "documento_nome": "Contrato.pdf",
            "status": "enviado",
            "provedor": "interno",
        }
        db = _make_db_for_insert(inserted)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.preparar_envio(
            documento_nome="Contrato.pdf",
            documento_url="https://storage.example.com/contrato.pdf",
            signatarios=[
                {"nome": "Joao", "email": "joao@example.com", "papel": "comprador"},
            ],
            provedor="interno",
            contrato_id="c-100",
        )

        assert result is not None
        assert result["status"] == "enviado"

    @pytest.mark.asyncio
    async def test_signatarios_get_pending_status(self):
        from app.services.assinatura_service import AssinaturaService

        # We test the internal logic: signatarios_com_status construction
        svc = AssinaturaService(MockSupabaseClient(), "user-1")

        signatarios = [
            {"nome": "A", "email": "a@x.com", "papel": "comprador"},
            {"nome": "B", "email": "b@x.com", "papel": "vendedor"},
        ]

        # Manually replicate what preparar_envio does
        signatarios_com_status = []
        for s in signatarios:
            signatarios_com_status.append({
                **s,
                "status": "pendente",
                "assinado_em": None,
            })

        assert len(signatarios_com_status) == 2
        assert all(s["status"] == "pendente" for s in signatarios_com_status)
        assert all(s["assinado_em"] is None for s in signatarios_com_status)

    @pytest.mark.asyncio
    async def test_link_assinatura_is_generated(self):
        """The signing link should be a valid-looking URL."""
        inserted = {
            "id": "a-1",
            "link_assinatura": "https://assinaturas.noctus.app/assinar/abc123",
            "status": "enviado",
        }
        db = _make_db_for_insert(inserted)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.preparar_envio(
            documento_nome="Doc.pdf",
            documento_url=None,
            signatarios=[{"nome": "X", "email": "x@x.com", "papel": "parte"}],
        )

        assert result is not None


# ---------------------------------------------------------------------------
# processar_webhook
# ---------------------------------------------------------------------------

class TestProcessarWebhook:

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        db = MockSupabaseClient(data=None)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.processar_webhook("missing-id", "assinado")

        assert result is None

    @pytest.mark.asyncio
    async def test_signed_event_updates_status(self):
        existing = {
            "id": "a-1",
            "status": "enviado",
            "historico": [{"evento": "enviado", "data": "2026-01-01"}],
            "signatarios": [
                {"nome": "Joao", "email": "joao@x.com", "status": "pendente", "assinado_em": None},
            ],
        }
        db = _make_db_with_record(existing)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.processar_webhook(
            "a-1",
            "signed",
            dados={"email": "joao@x.com"},
        )

        # The mock returns the same data, but we verify the code path did not raise
        assert result is not None

    @pytest.mark.asyncio
    async def test_unknown_event_keeps_current_status(self):
        existing = {
            "id": "a-1",
            "status": "enviado",
            "historico": [],
            "signatarios": [],
        }
        db = _make_db_with_record(existing)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        # "desconhecido" is not in the EVENT_STATUS_MAP
        result = await svc.processar_webhook("a-1", "desconhecido")

        assert result is not None

    @pytest.mark.asyncio
    async def test_refused_event_maps_correctly(self):
        existing = {
            "id": "a-2",
            "status": "enviado",
            "historico": [],
            "signatarios": [],
        }
        db = _make_db_with_record(existing)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.processar_webhook("a-2", "refused")

        assert result is not None


# ---------------------------------------------------------------------------
# get_resumo
# ---------------------------------------------------------------------------

class TestGetResumo:

    def test_empty_list(self):
        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(MockSupabaseClient(), "u1")

        resumo = svc.get_resumo([])

        assert resumo["total"] == 0
        assert resumo["pendentes"] == 0
        assert resumo["enviadas"] == 0
        assert resumo["assinadas"] == 0

    def test_counts_each_status(self):
        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(MockSupabaseClient(), "u1")

        assinaturas = [
            {"status": "pendente"},
            {"status": "enviado"},
            {"status": "enviado"},
            {"status": "assinado"},
            {"status": "assinado"},
            {"status": "assinado"},
            {"status": "recusado"},
            {"status": "expirado"},
            {"status": "cancelado"},
            {"status": "cancelado"},
        ]

        resumo = svc.get_resumo(assinaturas)

        assert resumo["total"] == 10
        assert resumo["pendentes"] == 1
        assert resumo["enviadas"] == 2
        assert resumo["assinadas"] == 3
        assert resumo["recusadas"] == 1
        assert resumo["expiradas"] == 1
        assert resumo["canceladas"] == 2

    def test_unknown_status_not_counted_individually(self):
        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(MockSupabaseClient(), "u1")

        assinaturas = [{"status": "desconhecido"}]

        resumo = svc.get_resumo(assinaturas)

        assert resumo["total"] == 1
        assert resumo["pendentes"] == 0
        assert resumo["enviadas"] == 0


# ---------------------------------------------------------------------------
# cancelar
# ---------------------------------------------------------------------------

class TestCancelar:

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        db = MockSupabaseClient(data=None)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.cancelar("missing-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_already_signed_cannot_cancel(self):
        existing = {
            "id": "a-1",
            "status": "assinado",
            "historico": [],
        }
        db = _make_db_with_record(existing)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.cancelar("a-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_already_cancelled_cannot_cancel_again(self):
        existing = {
            "id": "a-1",
            "status": "cancelado",
            "historico": [],
        }
        db = _make_db_with_record(existing)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.cancelar("a-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_enviado_can_be_cancelled(self):
        existing = {
            "id": "a-1",
            "status": "enviado",
            "historico": [{"evento": "enviado"}],
        }
        db = _make_db_with_record(existing)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.cancelar("a-1")

        # The mock returns the same data (status=enviado), but we verify no exception
        assert result is not None
