"""The official name (migration 071) and the stalled-extraction sweep (072).

WHAT THESE PIN
--------------
1. **The registration name is never touched.** `nome_completo` / `nome` belong
   to whoever registered the lead. Extraction writes `nome_oficial` and only
   `nome_oficial`, because the whole value of holding both is comparing them —
   and a reconciliation destroys the comparison one row at a time.
2. **A name read off a vision pass is a suggestion, not a fact.** It overwrites
   nothing until a human agrees.
3. **A stranded extraction is recovered, but not forever.** `processando` with
   nobody working on it is a silent error; retrying a doomed document on every
   pass is an unbounded vision bill.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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
NOME_DOC = "JOAO PEREIRA DA SILVA"


def _com_nome(confianca=ExtractionConfidence.ALTA, source=TextSource.TEXT_LAYER,
              nome=NOME_DOC) -> IdentityFields:
    return IdentityFields(
        data_nascimento=date(1980, 5, 12),
        data_nascimento_confianca=ExtractionConfidence.ALTA,
        data_nascimento_rotulo="DATA DE NASCIMENTO",
        nome=nome,
        nome_confianca=confianca,
        nome_rotulo="NOME",
        source=source,
    )


async def _setup(scoped, *, tipo="rg", cliente=None, doc_extra=None, storage=None):
    cid, did = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, **(cliente or {}))])
    path = f"{ORG_ID}/clientes/{cid}/{did}"
    row = {
        "id": did, "org_id": ORG_ID, "cliente_id": cid,
        "storage_path": path, "nome_original": f"{tipo}.pdf",
        "mime_type": "application/pdf", "tipo_documento": tipo,
        "deleted_at": None, "extracao_status": "pendente",
        "extracao_tentativas": 0,
    }
    row.update(doc_extra or {})
    scoped.set_table_data("cliente_documentos", [row])
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


class TestTheRegistrationNameIsNeverTouched:
    @pytest.mark.asyncio
    async def test_a_high_confidence_read_writes_nome_oficial_only(
        self, client, scoped
    ):
        cid, did, storage = await _setup(
            scoped, cliente={"nome": "Joao", "nome_completo": "Joao P Silva"}
        )
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_com_nome()),
        )
        row = _cliente(scoped, cid)

        assert out["aplicado_ao_cliente"]["nome_oficial"] is True
        assert row["nome_oficial"] == NOME_DOC
        assert row["nome_oficial_origem"] == "rg"
        assert row["nome_oficial_documento_id"] == did
        # 🔴 The registration's own values are byte-for-byte untouched.
        assert row["nome"] == "Joao"
        assert row["nome_completo"] == "Joao P Silva"

    @pytest.mark.asyncio
    async def test_an_empty_registration_is_still_not_filled_in(
        self, client, scoped
    ):
        """Not even "helpfully". An empty registration name is a fact about
        the registration, and backfilling it from a document would make the
        comparison read `confere` for a row that was never registered."""
        cid, did, storage = await _setup(scoped, cliente={"nome_completo": None})
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_com_nome()),
        )
        row = _cliente(scoped, cid)
        assert row["nome_oficial"] == NOME_DOC
        assert row.get("nome_completo") is None


class TestVisionReadsAreOnlySuggestions:
    @pytest.mark.asyncio
    async def test_a_baixa_name_never_reaches_the_client(self, client, scoped):
        cid, did, storage = await _setup(scoped)
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(
                _com_nome(ExtractionConfidence.BAIXA, TextSource.OCR)
            ),
        )
        assert out["aplicado_ao_cliente"]["nome_oficial"] is False
        assert _cliente(scoped, cid).get("nome_oficial") is None
        # …but it IS recorded on the document, as evidence to offer.
        assert _documento(scoped, did)["extracao_nome"] == NOME_DOC
        assert _documento(scoped, did)["extracao_nome_confianca"] == "baixa"

    @pytest.mark.asyncio
    async def test_it_is_offered_as_a_pending_suggestion(self, client, scoped):
        cid, did, storage = await _setup(scoped)
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(
                _com_nome(ExtractionConfidence.BAIXA, TextSource.OCR)
            ),
        )
        sugestoes = svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))
        assert sugestoes["nome_oficial"]["valor"] == NOME_DOC
        assert sugestoes["nome_oficial"]["documento_id"] == did

    @pytest.mark.asyncio
    async def test_confirming_applies_it_and_records_who_vouched(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped)
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(
                _com_nome(ExtractionConfidence.BAIXA, TextSource.OCR)
            ),
        )
        user = uuid4()
        out = svc.confirmar_sugestao(
            scoped, ORG_UUID, UUID(cid), UUID(did),
            item_key="nome_oficial", user_id=user,
        )
        row = _cliente(scoped, cid)

        assert out["confirmado"] is True
        assert row["nome_oficial"] == NOME_DOC
        # origem is the DOCUMENT, not 'manual' — the human added
        # accountability, not authorship.
        assert row["nome_oficial_origem"] == "rg"
        assert row["nome_oficial_confirmado_por"] == str(user)


class TestSecondDocumentDisagrees:
    @pytest.mark.asyncio
    async def test_the_newer_reading_wins_nome_oficial(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, cliente={"nome_oficial": "JOAO P SILVA",
                             "nome_oficial_origem": "cpf"}
        )
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_com_nome()),
        )
        row = _cliente(scoped, cid)
        assert row["nome_oficial"] == NOME_DOC
        assert row["nome_oficial_origem"] == "rg"

    @pytest.mark.asyncio
    async def test_an_identical_reading_is_a_no_op(self, client, scoped):
        """Same name modulo accents/case/spacing: nothing to restamp."""
        cid, did, storage = await _setup(
            scoped, cliente={"nome_oficial": "joão  pereira da silva"}
        )
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_com_nome()),
        )
        assert out["aplicado_ao_cliente"]["nome_oficial"] is False


class TestTheBirthdateRuleIsUnchanged:
    @pytest.mark.asyncio
    async def test_an_existing_birthdate_still_wins(self, client, scoped):
        """The two fields have different rules; changing one must not have
        quietly changed the other."""
        cid, did, storage = await _setup(
            scoped, cliente={"data_nascimento": "1975-01-01"}
        )
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_com_nome()),
        )
        assert out["aplicado_ao_cliente"]["data_nascimento"] is False
        assert _cliente(scoped, cid)["data_nascimento"] == "1975-01-01"
        # …while the name on the same read still landed.
        assert out["aplicado_ao_cliente"]["nome_oficial"] is True


def _old(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


class TestStalledExtractionSweep:
    @pytest.mark.asyncio
    async def test_a_document_stuck_in_processando_is_retried(self, client, scoped):
        """🔴 The silent error this exists for: the process died between
        stamping `processando` and writing a terminal status, and nothing
        would ever move it again."""
        cid, did, storage = await _setup(
            scoped,
            doc_extra={"extracao_status": "processando", "extracao_em": _old(60),
                       "extracao_tentativas": 1},
        )
        result = await svc.varrer_extracoes_pendentes(
            scoped, storage,
            extractor_factory=lambda _org: FakeIdentityExtractor(_com_nome()),
        )
        assert result["encontrados"] == 1
        assert result["retomados"] == 1
        assert _documento(scoped, did)["extracao_status"] == "ok"
        assert _cliente(scoped, cid)["nome_oficial"] == NOME_DOC

    @pytest.mark.asyncio
    async def test_a_recent_document_is_left_alone(self, client, scoped):
        """It may simply still be working. Racing it would double the bill
        and could interleave two writers on one row."""
        _cid, _did, storage = await _setup(
            scoped,
            doc_extra={"extracao_status": "processando", "extracao_em": _old(1)},
        )
        result = await svc.varrer_extracoes_pendentes(scoped, storage)
        assert result["encontrados"] == 0

    @pytest.mark.asyncio
    async def test_retries_are_bounded(self, client, scoped):
        """A deterministically-broken document must stop costing money."""
        _cid, did, storage = await _setup(
            scoped,
            doc_extra={"extracao_status": "processando", "extracao_em": _old(60),
                       "extracao_tentativas": svc.MAX_TENTATIVAS},
        )
        result = await svc.varrer_extracoes_pendentes(
            scoped, storage,
            extractor_factory=lambda _org: FakeIdentityExtractor(_com_nome()),
        )
        doc = _documento(scoped, did)

        assert result["esgotados"] == 1
        assert result["retomados"] == 0
        # Terminal, visible, and explains itself — not a silent `processando`.
        assert doc["extracao_status"] == "erro"
        assert "tentativas" in doc["extracao_erro"]

    @pytest.mark.asyncio
    async def test_a_terminal_document_is_never_swept(self, client, scoped):
        _cid, _did, storage = await _setup(
            scoped,
            doc_extra={"extracao_status": "ok", "extracao_em": _old(600)},
        )
        assert (await svc.varrer_extracoes_pendentes(scoped, storage))["encontrados"] == 0

    @pytest.mark.asyncio
    async def test_the_attempt_counter_advances_on_each_read(self, client, scoped):
        cid, did, storage = await _setup(scoped)
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_com_nome()),
        )
        assert _documento(scoped, did)["extracao_tentativas"] == 1
