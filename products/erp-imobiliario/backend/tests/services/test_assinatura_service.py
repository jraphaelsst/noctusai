"""
Unit tests for AssinaturaService — document preparation (via the seed
`signature` IO module), webhook processing, cancellation, summary.

Provider interaction is exercised through the constructor's
`adapter_factory` / `http_client` DI seams (`KB § PATTERNS/backend/
di-test-seam.md`) — never by monkeypatching `AssinaturaService` or the
seed module's internals.
"""
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock

from noctusai_lib.integrations.signature import (
    EventoAssinatura,
    FakeSignatureAdapter,
    ProvedorNaoConfigurado,
    make_signature_adapter,
)
from tests.conftest import MockSupabaseClient, MockSupabaseResponse


def _evento(external_id: str = "ext-1", status: str = "concluido") -> EventoAssinatura:
    from datetime import datetime, timezone

    return EventoAssinatura(
        external_id=external_id,
        status=status,
        provedor="d4sign",
        ocorrido_em=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db_with_record(record):
    """Return a MockSupabaseClient whose default query returns *record*."""
    db = MockSupabaseClient(data=record)
    return db


def _make_db_for_webhook(record):
    """A DB double that returns *record* for the SELECT-by-`external_id`
    lookup and records every `.update(...)` payload in `update_calls` —
    so a webhook regression test can assert not just "it ran" but WHAT
    (or whether anything) was persisted, including a refused/no-op
    transition never issuing an update at all (2026-09-20 wiring audit,
    task 4: "observe the refusal, don't just assert it runs")."""
    db = MockSupabaseClient()
    update_calls: list[dict] = []

    builder = MagicMock()
    builder.select = MagicMock(return_value=builder)
    builder.eq = MagicMock(return_value=builder)
    builder.single = MagicMock(return_value=builder)

    def _update(payload):
        update_calls.append(payload)
        return builder

    builder.update = MagicMock(side_effect=_update)
    builder.execute = MagicMock(return_value=MockSupabaseResponse(data=record))
    db._tables["assinaturas"] = builder
    return db, update_calls


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


def _fake_http_client(conteudo: bytes = b"%PDF-1.4 fake doc") -> AsyncMock:
    """An `httpx.AsyncClient` double whose `.get()` returns a 200 with
    *conteudo* — the DI seam `AssinaturaService._baixar_documento` reaches
    for instead of hitting the network (mirrors
    `test_certidoes_service.py`'s `AsyncMock(spec=httpx.AsyncClient)`)."""
    resp = httpx.Response(200, content=conteudo, request=httpx.Request("GET", "https://x/doc.pdf"))
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=resp)
    return client


def _fake_adapter_factory(adapter=None):
    """An `adapter_factory` DI seam that always returns *adapter* (a fresh
    `FakeSignatureAdapter()` by default), ignoring the `real=`/`provedor=`/
    `org_id=` kwargs `AssinaturaService` always passes."""
    instance = adapter if adapter is not None else FakeSignatureAdapter()

    def _factory(*, real, provedor, org_id):
        return instance

    return _factory, instance


def _sem_credenciais_factory():
    """An `adapter_factory` that drives the REAL `make_signature_adapter`
    through its own `resolver` DI seam with every credential missing —
    proving `real=True` + no credentials refuses rather than silently
    returning a Fake. No monkeypatching: `resolver` is the seed's own seam."""

    def _factory(*, real, provedor, org_id):
        return make_signature_adapter(
            real=real, provedor=provedor, org_id=org_id, resolver=lambda key, org: None
        )

    return _factory


# ---------------------------------------------------------------------------
# D4SIGN_STATUS_MAP
# ---------------------------------------------------------------------------

class TestD4SignStatusMap:
    def test_maps_every_seed_status_to_an_erp_status(self):
        from app.services.assinatura_service import AssinaturaService

        assert AssinaturaService.D4SIGN_STATUS_MAP["concluido"] == "assinado"
        assert AssinaturaService.D4SIGN_STATUS_MAP["cancelado"] == "cancelado"
        assert AssinaturaService.D4SIGN_STATUS_MAP["expirado"] == "expirado"
        assert AssinaturaService.D4SIGN_STATUS_MAP["pendente"] == "enviado"
        assert AssinaturaService.D4SIGN_STATUS_MAP["parcial"] == "enviado"


# ---------------------------------------------------------------------------
# preparar_envio — happy path through the Fake
# ---------------------------------------------------------------------------

class TestPrepararEnvioHappyPath:

    @pytest.mark.asyncio
    async def test_creates_assinatura_record_via_fake_adapter(self):
        inserted = {
            "id": "a-1",
            "documento_nome": "Contrato.pdf",
            "status": "enviado",
            "provedor": "d4sign",
        }
        db = _make_db_for_insert(inserted)
        factory, fake = _fake_adapter_factory()

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(
            db, "user-1",
            adapter_factory=factory,
            http_client=_fake_http_client(),
        )

        result = await svc.preparar_envio(
            documento_nome="Contrato.pdf",
            documento_url="https://storage.example.com/contrato.pdf",
            signatarios=[
                {"nome": "Joao", "email": "joao@example.com", "papel": "comprador"},
            ],
            provedor="d4sign",
            contrato_id="c-100",
        )

        assert result is not None
        assert result["status"] == "enviado"
        # The Fake actually ran criar_envelope — proves the adapter swap is wired.
        assert fake.calls == [("criar_envelope", "Contrato.pdf")]

    @pytest.mark.asyncio
    async def test_insert_payload_carries_envelope_fields(self):
        db = _make_db_for_insert({"id": "a-1", "status": "enviado"})
        factory, _fake = _fake_adapter_factory()

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(
            db, "user-1",
            adapter_factory=factory,
            http_client=_fake_http_client(),
        )

        await svc.preparar_envio(
            documento_nome="Doc.pdf",
            documento_url="https://storage.example.com/doc.pdf",
            signatarios=[{"nome": "X", "email": "x@x.com", "papel": "parte"}],
            provedor="d4sign",
        )

        insert_call = db._tables["assinaturas"].insert.call_args
        payload = insert_call.args[0]
        assert payload["link_assinatura"].startswith("https://fake.assinatura.local/")
        assert payload["external_id"].startswith("fake-")
        assert payload["provedor"] == "d4sign"
        assert payload["signatarios"][0]["status"] == "pendente"
        assert payload["signatarios"][0]["assinado_em"] is None
        # dry_run is gone — there is no more mock-dressed-as-real concept.
        assert "dry_run" not in payload["historico"][0]


# ---------------------------------------------------------------------------
# preparar_envio — refusals (no silent fallback)
# ---------------------------------------------------------------------------

class TestPrepararEnvioRefusals:

    @pytest.mark.asyncio
    async def test_unconfigured_org_is_refused_not_mocked(self):
        """real=True + no D4Sign credentials -> ProvedorNaoConfigurado,
        never a mock envelope (contract F1/§0)."""
        db = _make_db_for_insert({"id": "a-1"})

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(
            db, "user-1",
            org_id="org-1",
            adapter_factory=_sem_credenciais_factory(),
            http_client=_fake_http_client(),
        )

        with pytest.raises(ProvedorNaoConfigurado) as exc_info:
            await svc.preparar_envio(
                documento_nome="Contrato.pdf",
                documento_url="https://storage.example.com/contrato.pdf",
                signatarios=[{"nome": "Joao", "email": "joao@example.com", "papel": "comprador"}],
                provedor="d4sign",
            )

        assert "d4sign_api_token" in exc_info.value.faltando
        assert "d4sign_crypt_key" in exc_info.value.faltando
        assert "d4sign_safe_uuid" in exc_info.value.faltando
        # No row was ever inserted for a refused envelope.
        db._tables["assinaturas"].insert.assert_not_called()

    @pytest.mark.asyncio
    async def test_unsupported_provider_named_in_refusal(self):
        """ClickSign/DocuSign are not implemented in this pass — an org
        pointing at either gets a typed refusal naming it, not a silent
        fallback to a mock (contract §5)."""
        db = _make_db_for_insert({"id": "a-1"})
        factory, fake = _fake_adapter_factory()

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1", adapter_factory=factory)

        for provedor in ("clicksign", "docusign", "interno"):
            with pytest.raises(ProvedorNaoConfigurado) as exc_info:
                await svc.preparar_envio(
                    documento_nome="Contrato.pdf",
                    documento_url="https://storage.example.com/contrato.pdf",
                    signatarios=[{"nome": "Joao", "email": "joao@example.com", "papel": "comprador"}],
                    provedor=provedor,
                )
            assert provedor in exc_info.value.faltando[0]

        # The Fake was never reached for any of them — refusal happens
        # before any adapter call.
        assert fake.calls == []

    @pytest.mark.asyncio
    async def test_missing_documento_url_raises_value_error(self):
        db = _make_db_for_insert({"id": "a-1"})
        factory, fake = _fake_adapter_factory()

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1", adapter_factory=factory)

        with pytest.raises(ValueError):
            await svc.preparar_envio(
                documento_nome="Doc.pdf",
                documento_url=None,
                signatarios=[{"nome": "X", "email": "x@x.com", "papel": "parte"}],
                provedor="d4sign",
            )
        assert fake.calls == []

    @pytest.mark.asyncio
    async def test_document_download_failure_propagates(self):
        db = _make_db_for_insert({"id": "a-1"})
        factory, _fake = _fake_adapter_factory()

        broken_client = AsyncMock(spec=httpx.AsyncClient)
        broken_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1", adapter_factory=factory, http_client=broken_client)

        with pytest.raises(httpx.HTTPError):
            await svc.preparar_envio(
                documento_nome="Doc.pdf",
                documento_url="https://storage.example.com/doc.pdf",
                signatarios=[{"nome": "X", "email": "x@x.com", "papel": "parte"}],
                provedor="d4sign",
            )


# ---------------------------------------------------------------------------
# processar_webhook
# ---------------------------------------------------------------------------

class TestProcessarWebhook:

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        db = MockSupabaseClient(data=None)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.processar_webhook(_evento(external_id="missing-id"))

        assert result is None

    @pytest.mark.asyncio
    async def test_looks_up_by_external_id_not_erps_own_id(self):
        """2026-09-20 wiring audit, task 3: migration 047's `external_id`
        column was written at send time and never read by anything —
        D4Sign has no way to know erp's own `id`."""
        existing = {"id": "a-1", "external_id": "d4sign-ext-1", "status": "enviado", "historico": []}
        db, update_calls = _make_db_for_webhook(existing)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.processar_webhook(_evento(external_id="d4sign-ext-1", status="concluido"))

        assert result is not None
        db._tables["assinaturas"].eq.assert_any_call("external_id", "d4sign-ext-1")
        assert update_calls[-1]["status"] == "assinado"
        assert update_calls[-1]["data_assinatura"] is not None

    @pytest.mark.asyncio
    async def test_concluido_event_sets_assinado_and_data_assinatura(self):
        existing = {
            "id": "a-1",
            "external_id": "ext-1",
            "status": "enviado",
            "historico": [{"evento": "enviado", "data": "2026-01-01"}],
        }
        db, update_calls = _make_db_for_webhook(existing)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.processar_webhook(_evento(status="concluido"))

        assert result is not None
        assert update_calls[-1]["status"] == "assinado"
        assert update_calls[-1]["data_assinatura"] is not None

    @pytest.mark.asyncio
    async def test_cancelado_event_sets_cancelado(self):
        existing = {"id": "a-1", "external_id": "ext-1", "status": "enviado", "historico": []}
        db, update_calls = _make_db_for_webhook(existing)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.processar_webhook(_evento(status="cancelado"))

        assert result is not None
        assert update_calls[-1]["status"] == "cancelado"
        assert "data_assinatura" not in update_calls[-1]

    @pytest.mark.asyncio
    async def test_unknown_status_is_a_noop_not_a_crash(self):
        existing = {"id": "a-1", "external_id": "ext-1", "status": "enviado", "historico": []}
        db, update_calls = _make_db_for_webhook(existing)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        # "desconhecido" is not a StatusAssinatura the seed adapter would
        # ever produce, but the map lookup must degrade gracefully anyway.
        result = await svc.processar_webhook(_evento(status="desconhecido"))

        assert result == existing
        assert update_calls == []

    @pytest.mark.asyncio
    async def test_regressive_transition_off_a_terminal_status_is_refused(self):
        """2026-09-20 wiring audit, task 4 — the exact scenario the audit
        named: a replayed `type_post=5` ("cancelado") delivered AFTER the
        contract already reached `concluido` (erp status `assinado`) must
        NOT regress it. Observe the refusal directly: no `.update(...)`
        call happens at all, not merely "the call didn't raise"."""
        existing = {"id": "a-1", "external_id": "ext-1", "status": "assinado", "historico": []}
        db, update_calls = _make_db_for_webhook(existing)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.processar_webhook(_evento(status="cancelado"))

        assert result == existing  # unchanged row returned, not None and not mutated
        assert update_calls == []  # the write itself never happened

    @pytest.mark.asyncio
    async def test_replaying_the_same_terminal_status_is_allowed(self):
        """The idempotent-replay case (a provider retry of the identical
        event) must NOT be refused by the monotonic guard — only a
        DIFFERENT value over a terminal status is a regression."""
        existing = {"id": "a-1", "external_id": "ext-1", "status": "assinado", "historico": []}
        db, update_calls = _make_db_for_webhook(existing)

        from app.services.assinatura_service import AssinaturaService
        svc = AssinaturaService(db, "user-1")

        result = await svc.processar_webhook(_evento(status="concluido"))

        assert result is not None
        assert update_calls[-1]["status"] == "assinado"


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
