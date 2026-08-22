"""Birthdate extraction from an identity document (migration 068).

WHAT THESE TESTS PIN
--------------------
Three rules, each protecting something a later refactor would find tempting to
relax:

1. **Only a high-confidence read is written.** A guess stored as a fact is
   worse than a blank: a missing birthday is visibly missing, a wrong one is
   not, and nobody re-checks a field that already looks filled in.
2. **First writer wins; a human always outranks the machine.** Re-uploading a
   document must not rewrite a value someone already corrected by hand.
3. **Extraction is a logged content access.** Opening the bytes is a read under
   migration 057's contract, and it is logged as `extract` — not as a `view` by
   a null user, which would launder a machine read as a human one.

Everything runs against `FakeIdentityExtractor` through the DI seam, so no test
here touches a vision model.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.integrations.documents import (
    ExtractionConfidence,
    FakeIdentityExtractor,
    IdentityFields,
    TextSource,
)
from noctusai_lib.integrations.storage import FakeStorageBackend
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

BUCKET = "social-wiring-documentos"
ORG_UUID = UUID(ORG_ID)


def _alta(value=date(1980, 5, 12)) -> IdentityFields:
    return IdentityFields(
        data_nascimento=value,
        confidence=ExtractionConfidence.ALTA,
        source=TextSource.TEXT_LAYER,
        matched_label="DATA DE NASCIMENTO",
    )


def _baixa(value=date(1980, 5, 12)) -> IdentityFields:
    return IdentityFields(
        data_nascimento=value,
        confidence=ExtractionConfidence.BAIXA,
        source=TextSource.OCR,
    )


async def _setup(scoped, *, tipo="rg", cliente=None, storage=None):
    """Seed one cliente + one stored document, and return their ids."""
    cid, did = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, **(cliente or {}))])
    path = f"{ORG_ID}/clientes/{cid}/{did}"
    scoped.set_table_data("cliente_documentos", [{
        "id": did, "org_id": ORG_ID, "cliente_id": cid,
        "storage_path": path, "nome_original": f"{tipo}.pdf",
        "mime_type": "application/pdf", "tipo_documento": tipo,
        "deleted_at": None, "extracao_status": "pendente",
    }])
    scoped.set_table_data("cliente_documento_acessos", [])
    storage = storage or FakeStorageBackend()
    await storage.put(
        bucket=BUCKET, key=path, data=b"%PDF-1.4 fake", content_type="application/pdf"
    )
    return cid, did, storage


def _cliente(scoped, cid) -> dict:
    return [r for r in scoped.table("clientes").select("*").execute().data
            if r["id"] == cid][0]


def _documento(scoped, did) -> dict:
    return [r for r in scoped.table("cliente_documentos").select("*").execute().data
            if r["id"] == did][0]


class TestWhichTypesAreRead:
    @pytest.mark.parametrize("tipo,expected", [
        ("rg", True), ("cpf", True), ("cnh", True),
        ("contrato", False), ("foto_imovel", False), ("comprovante_endereco", False),
    ])
    def test_only_identity_documents_are_read(self, tipo, expected):
        assert svc.deve_extrair(tipo) is expected

    @pytest.mark.asyncio
    async def test_a_non_identity_document_is_refused_outright(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="contrato")
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_alta()),
        )
        assert out["erro"] == "tipo_nao_extraivel"
        assert _cliente(scoped, cid).get("data_nascimento") is None


class TestOnlyHighConfidenceIsWritten:
    @pytest.mark.asyncio
    async def test_high_confidence_fills_the_client_and_records_provenance(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped)
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_alta()),
        )
        assert out["aplicado_ao_cliente"] is True

        c = _cliente(scoped, cid)
        assert c["data_nascimento"] == "1980-05-12"
        assert c["data_nascimento_origem"] == "rg", "origin must name the document type"
        assert c["data_nascimento_documento_id"] == did

    @pytest.mark.asyncio
    async def test_low_confidence_never_touches_the_client(self, client, scoped):
        """🔴 The suggestion is kept ON THE DOCUMENT, where a human can
        confirm it. A guess written into the record is indistinguishable
        from a fact, and nobody re-checks a field that looks filled in."""
        cid, did, storage = await _setup(scoped)
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_baixa()),
        )
        assert out["aplicado_ao_cliente"] is False
        assert _cliente(scoped, cid).get("data_nascimento") is None

        doc = _documento(scoped, did)
        assert doc["extracao_data_nascimento"] == "1980-05-12"
        assert doc["extracao_confianca"] == "baixa"
        assert doc["extracao_status"] == "ok"

    @pytest.mark.asyncio
    async def test_a_legible_document_with_no_birthdate_is_not_an_error(
        self, client, scoped
    ):
        """Distinct from a failure — retrying it would be pointless."""
        cid, did, storage = await _setup(scoped)
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(IdentityFields(source=TextSource.OCR)),
        )
        assert out["status"] == "sem_dados"
        assert _documento(scoped, did)["extracao_status"] == "sem_dados"
        assert _documento(scoped, did)["extracao_erro"] is None


class TestFirstWriterWins:
    @pytest.mark.asyncio
    async def test_an_existing_birthdate_is_never_overwritten(self, client, scoped):
        """"Whichever comes first" — the CPF must not rewrite what the RG
        already established."""
        cid, did, storage = await _setup(
            scoped, tipo="cpf",
            cliente={"data_nascimento": "1975-11-03", "data_nascimento_origem": "rg"},
        )
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_alta(date(1980, 5, 12))),
        )
        assert out["aplicado_ao_cliente"] is False
        c = _cliente(scoped, cid)
        assert c["data_nascimento"] == "1975-11-03"
        assert c["data_nascimento_origem"] == "rg"

    @pytest.mark.asyncio
    async def test_a_manual_value_outranks_the_machine(self, client, scoped):
        """🔴 Someone typed this in. A later scan must not quietly disagree
        with them."""
        cid, did, storage = await _setup(
            scoped,
            cliente={"data_nascimento": "1975-11-03", "data_nascimento_origem": "manual"},
        )
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_alta()),
        )
        assert _cliente(scoped, cid)["data_nascimento"] == "1975-11-03"


class TestExtractionIsALoggedAccess:
    @pytest.mark.asyncio
    async def test_reading_the_bytes_appends_an_extract_row(self, client, scoped):
        """🔴 Migration 057: every read of a document's CONTENT is logged.
        An automated read is still a read."""
        cid, did, storage = await _setup(scoped)
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_alta()),
        )
        acessos = scoped.table("cliente_documento_acessos").select("*").execute().data
        assert [a["acao"] for a in acessos] == ["extract"], (
            "logged as something other than 'extract' — a machine read must "
            "not be indistinguishable from a human 'view'"
        )
        assert acessos[0]["usuario_id"] is None
        assert acessos[0]["documento_id"] == did

    @pytest.mark.asyncio
    async def test_the_access_is_logged_even_when_extraction_then_fails(
        self, client, scoped
    ):
        """An access log that only records successful reads is not an
        access log — the bytes were opened either way."""
        cid, did, storage = await _setup(scoped)

        class _Boom:
            async def extract(self, content, **kw):
                return IdentityFields(error="resolver_failed", error_message="vision down")

        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did), extractor=_Boom(),
        )
        acessos = scoped.table("cliente_documento_acessos").select("*").execute().data
        assert [a["acao"] for a in acessos] == ["extract"]
        assert _documento(scoped, did)["extracao_status"] == "erro"


class TestFailuresAreRecordedNotRaised:
    @pytest.mark.asyncio
    async def test_a_missing_storage_object_is_recorded(self, client, scoped):
        """Detached job: an exception here would surface nowhere and leave
        the document stuck in `processando` forever."""
        cid, did, _ = await _setup(scoped)
        out = await svc.extrair_identidade(
            scoped, FakeStorageBackend(), ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_alta()),
        )
        assert out["erro"] == "objeto_ausente"
        assert _documento(scoped, did)["extracao_status"] == "erro"

    @pytest.mark.asyncio
    async def test_a_document_deleted_before_the_job_ran_is_not_read(
        self, client, scoped
    ):
        """🔴 Reading it now would be an access to something the client
        asked us to forget."""
        cid, did, storage = await _setup(scoped)
        rows = scoped.table("cliente_documentos").select("*").execute().data
        rows[0]["deleted_at"] = "2026-08-22T00:00:00+00:00"
        scoped.set_table_data("cliente_documentos", rows)

        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_alta()),
        )
        assert out["erro"] == "documento_removido"
        assert scoped.table("cliente_documento_acessos").select("*").execute().data == []


class TestDerivedTickFollowsForFree:
    @pytest.mark.asyncio
    async def test_a_successful_extraction_ticks_data_nascimento(self, client, scoped):
        """The whole point of deriving: nothing notifies the checklist."""
        from app.modules.card_hub import documento_checklist_service as checklist

        cid, did, storage = await _setup(scoped)
        scoped.set_table_data("cliente_documento_checklist", [])

        before = checklist.listar(scoped, ORG_UUID, UUID(cid))
        assert {i["key"]: i["concluido"] for i in before["items"]}["data_nascimento"] is False

        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_alta()),
        )
        after = checklist.listar(scoped, ORG_UUID, UUID(cid))
        by_key = {i["key"]: i for i in after["items"]}
        assert by_key["data_nascimento"]["concluido"] is True
        assert by_key["rg"]["concluido"] is True, "the upload itself satisfies RG"
