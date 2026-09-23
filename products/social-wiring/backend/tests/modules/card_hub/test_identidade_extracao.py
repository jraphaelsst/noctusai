"""Birthdate extraction from an identity document (migration 068).

WHAT THESE TESTS PIN
--------------------
Three rules, each protecting something a later refactor would find tempting to
relax:

1. **D1 (migration 153): any read fills an EMPTY field, machine-pending.** It
   used to be "only a high-confidence read is written"; the owner's D1
   decision moved the human check to the contract's validation gate, which
   lists every machine value not yet confirmed (`_confirmado_em IS NULL`) —
   so a vision read is no longer lost, and still never silently trusted.
2. **First writer wins; a human always outranks the machine.** Re-uploading a
   document must not rewrite a value someone already corrected by hand.
3. **Extraction is a logged content access.** Opening the bytes is a read under
   migration 057's contract, and it is logged as `extract` — not as a `view` by
   a null user, which would launder a machine read as a human one.

Everything runs against `FakeIdentityExtractor` through the DI seam, so no test
here touches a vision model — EXCEPT `TestDataCasamentoEDataEmissaoViaLadderReal`
at the bottom, which runs the REAL `LadderIdentityExtractor` (a stubbed
resolver stands in for the vision rung, per `test_civil_status.py`'s own
`TestCivilStatusWiring` pattern) to prove the seed's parser wiring and this
service's storage wiring compose end to end, not just against canned Fake data.
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
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.primitives.exceptions import ValidationError_
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

BUCKET = "social-wiring-documentos"
ORG_UUID = UUID(ORG_ID)


def _alta(value=date(1980, 5, 12)) -> IdentityFields:
    return IdentityFields(
        data_nascimento=value,
        data_nascimento_confianca=ExtractionConfidence.ALTA,
        source=TextSource.TEXT_LAYER,
        data_nascimento_rotulo="DATA DE NASCIMENTO",
    )


def _baixa(value=date(1980, 5, 12)) -> IdentityFields:
    return IdentityFields(
        data_nascimento=value,
        data_nascimento_confianca=ExtractionConfidence.BAIXA,
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
        ("rg", True), ("cpf", True), ("cnh", True), ("certidao_casamento", True),
        # Migration 110 — a marriage/divórcio/óbito is averbado on a birth
        # certificate's margin too, not only on a certidão de casamento.
        ("certidao_nascimento", True),
        ("contrato", False), ("foto_imovel", False),
        # Migration 153 — read for its ADDRESS only (`TIPOS_ENDERECO`).
        ("comprovante_endereco", True),
        # `outro` is where the three certidões this org holds were actually
        # filed, which is why none of them was ever read (migration 103).
        ("outro", False),
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


class TestD1FillEmptyAtAnyConfidence:
    @pytest.mark.asyncio
    async def test_high_confidence_fills_the_client_and_records_provenance(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped)
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_alta()),
        )
        assert out["aplicado_ao_cliente"]["data_nascimento"] is True

        c = _cliente(scoped, cid)
        assert c["data_nascimento"] == "1980-05-12"
        assert c["data_nascimento_origem"] == "rg", "origin must name the document type"
        assert c["data_nascimento_documento_id"] == did

    @pytest.mark.asyncio
    async def test_low_confidence_fills_an_empty_field_machine_pending(
        self, client, scoped
    ):
        """🔴 D1 (migration 153) superseded "only `alta` is written": a
        low-confidence read fills an EMPTY field, stamped with provenance and
        left unconfirmed — the contract's validation gate lists it as
        machine-pending, and THAT is where a human vouches for it. The
        confidence stays on the document row for the gate to show."""
        cid, did, storage = await _setup(scoped)
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_baixa()),
        )
        assert out["aplicado_ao_cliente"]["data_nascimento"] is True
        c = _cliente(scoped, cid)
        assert c["data_nascimento"] == "1980-05-12"
        assert c["data_nascimento_origem"] == "rg"
        assert c.get("data_nascimento_confirmado_em") is None

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
        assert out["aplicado_ao_cliente"]["data_nascimento"] is False
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
        # Since the `rg`/`cpf` collapse (2026-09-23) the upload alone no longer
        # satisfies the identity item: `_alta()` reads no RG/CPF, so the item
        # stays open and names both numbers — while still listing the file.
        identidade = by_key["identidade"]
        assert identidade["concluido"] is False
        assert identidade["faltando"] == ["rg", "cpf"]
        legado = {s["tipo_documento"]: s for s in identidade["documentos"]}
        assert legado["rg"]["documento"]["id"] == did


class TestGeneroIsTheThirdExtractedField:
    """🔴 Migration 073. The point of these is that almost nothing was written
    to support them.

    `CAMPOS` is table-driven, so `genero` is ONE entry there plus one mapping
    in `_valores_lidos` — the apply, suggest, confirm, provenance and
    access-log paths are the same code the birthdate and the name already ran
    through. These tests exist to prove that claim rather than to assume it.
    """

    @staticmethod
    def _com_genero(confianca=ExtractionConfidence.ALTA) -> IdentityFields:
        return IdentityFields(
            genero="Masculino",
            genero_confianca=confianca,
            genero_rotulo="SEXO",
            source=TextSource.TEXT_LAYER,
        )

    @pytest.mark.asyncio
    async def test_a_confident_read_fills_the_column_and_stamps_provenance(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped)
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(self._com_genero()),
        )
        row = _cliente(scoped, cid)
        assert row["genero"] == "Masculino"
        # Attributable and correctable, never an anonymous fact in a column.
        assert row["genero_origem"] == "rg"
        assert row["genero_documento_id"] == did

    @pytest.mark.asyncio
    async def test_a_low_confidence_read_fills_an_empty_field_machine_pending(
        self, client, scoped
    ):
        """D1 (migration 153): filled, unconfirmed — the validation gate is
        where a human vouches for it."""
        cid, did, storage = await _setup(scoped)
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(
                self._com_genero(ExtractionConfidence.BAIXA)
            ),
        )
        row = _cliente(scoped, cid)
        assert row["genero"] == "Masculino"
        assert row.get("genero_confirmado_em") is None
        assert _documento(scoped, did)["extracao_genero_confianca"] == "baixa"

    @pytest.mark.asyncio
    async def test_a_typed_genero_is_not_overwritten_by_a_later_document(
        self, client, scoped
    ):
        """First-writer-wins, like the birthdate and unlike `nome_oficial`.

        `genero` is a REGISTRATION field an operator fills in on the card, so a
        later RG must not silently replace what a person entered. The name may
        overwrite only because it is held BESIDE the registration name rather
        than being it — there is no such second column here.
        """
        cid, did, storage = await _setup(
            scoped, cliente={"genero": "Feminino", "genero_origem": "manual"}
        )
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(self._com_genero()),
        )
        assert _cliente(scoped, cid)["genero"] == "Feminino"

    @pytest.mark.asyncio
    async def test_the_checklist_item_ticks_itself_off_the_document(
        self, client, scoped
    ):
        """No checklist call anywhere — the tick is derived from the column the
        extraction just filled."""
        from app.modules.card_hub import documento_checklist_service as checklist_svc

        cid, did, storage = await _setup(scoped)
        scoped.set_table_data("cliente_documento_checklist", [])
        antes = checklist_svc.listar(scoped, ORG_UUID, UUID(cid))
        assert {i["key"]: i["concluido"] for i in antes["items"]}["genero"] is False

        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(self._com_genero()),
        )
        depois = checklist_svc.listar(scoped, ORG_UUID, UUID(cid))
        assert {i["key"]: i["concluido"] for i in depois["items"]}["genero"] is True


class TestUmaCertidaoEhLidaPorInteiro:
    """The page cap is a property of the document TYPE.

    🔴 TRUNCATION HERE INVERTS THE ANSWER, it does not degrade it. A certidão
    de casamento states the marriage on page 1 as a LABELLED form ("regime de
    bens: comunhão parcial") and carries the AVERBAÇÃO that dissolved it —
    the divorce, the name reversion — as prose further in. On the three
    certidões this org holds (2026-09-07) ALL THREE parties are divorced and
    ALL THREE documents read "casado" on their first page.

    So this rule is the precondition for `certidao_casamento` being
    extractable at all: registering the type without it would start writing
    confident wrong estado-civil values where today the document is simply
    never read.
    """

    def test_a_certidao_asks_for_every_page(self):
        assert svc.paginas_maximas("certidao_casamento") is None

    def test_a_certidao_de_nascimento_asks_for_every_page_too(self):
        """Migration 110 — the averbação that amends a birth certificate is
        just as far into the document as it is on a certidão de casamento."""
        assert svc.paginas_maximas("certidao_nascimento") is None

    @pytest.mark.parametrize("tipo", ["rg", "cpf", "cnh", "contrato"])
    def test_everything_else_leaves_the_default_to_the_adapter(self, tipo):
        # The sentinel, NOT the literal 3: the cost trade-off is owned by the
        # seed adapter, and copying its default here would diverge silently
        # the day it changes.
        assert svc.paginas_maximas(tipo) == -1

    def test_the_two_sets_agree(self):
        """A type that must be read whole but is not extractable would be a
        rule nothing consults."""
        assert svc.TIPOS_LEITURA_INTEGRAL <= svc.TIPOS_EXTRAIVEIS

    @pytest.mark.asyncio
    async def test_the_cap_reaches_the_extractor_factory(self, client, scoped, monkeypatch):
        """The wiring, not just the mapping.

        A correct `paginas_maximas` still truncates every certidão if nobody
        threads it into the factory — and that failure is invisible, because
        the run succeeds and simply reads three pages.
        """
        visto: dict = {}
        import app.modules.card_hub.identidade_extracao_service as mod

        def _fabrica(**kw):
            visto.update(kw)
            return FakeIdentityExtractor(_alta())

        # self-patch-ok: substitutes the SEED factory at this module's import
        # site (a third-party-shaped boundary), not this module's own logic —
        # `extrair_identidade` builds the extractor internally and takes no
        # factory seam to pass instead.
        monkeypatch.setattr(mod, "make_identity_extractor", _fabrica)

        cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
        await svc.extrair_identidade(scoped, storage, ORG_UUID, UUID(cid), UUID(did))

        assert visto.get("max_pages") is None, "a certidão must be read whole"


class TestEstadoCivilERegimeBensSaoExtraidos:
    """Migration 110. `CAMPOS` is table-driven — same claim
    `TestGeneroIsTheThirdExtractedField` proves for `genero`, now for the
    pair `civil_status.py` predicted its own arrival on `IdentityFields`'
    docstring: `estado_civil` and `regime_bens` ride the exact same apply /
    suggest / confirm / provenance / access-log code every other CAMPO does.
    """

    @staticmethod
    def _com_civil(confianca=ExtractionConfidence.ALTA) -> IdentityFields:
        return IdentityFields(
            estado_civil="casado",
            estado_civil_confianca=confianca,
            estado_civil_rotulo="ESTADO CIVIL",
            regime_bens="comunhao_parcial",
            regime_bens_confianca=confianca,
            regime_bens_rotulo="REGIME DE BENS",
            source=TextSource.TEXT_LAYER,
        )

    @pytest.mark.asyncio
    async def test_a_confident_read_fills_both_columns_and_stamps_provenance(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(self._com_civil()),
        )
        assert out["aplicado_ao_cliente"]["estado_civil"] is True
        assert out["aplicado_ao_cliente"]["regime_bens"] is True

        row = _cliente(scoped, cid)
        assert row["estado_civil"] == "casado"
        assert row["estado_civil_origem"] == "certidao_casamento"
        assert row["estado_civil_documento_id"] == did
        assert row["regime_bens"] == "comunhao_parcial"
        assert row["regime_bens_origem"] == "certidao_casamento"

    @pytest.mark.asyncio
    async def test_a_low_confidence_read_fills_empty_fields_machine_pending(
        self, client, scoped
    ):
        """D1 (migration 153)."""
        cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(
                self._com_civil(ExtractionConfidence.BAIXA)
            ),
        )
        row = _cliente(scoped, cid)
        assert row["estado_civil"] == "casado"
        assert row["regime_bens"] == "comunhao_parcial"
        assert row.get("estado_civil_confirmado_em") is None

        doc = _documento(scoped, did)
        assert doc["extracao_estado_civil"] == "casado"
        assert doc["extracao_regime_bens"] == "comunhao_parcial"

    @pytest.mark.asyncio
    async def test_an_existing_value_is_not_overwritten(self, client, scoped):
        """`sobrescreve=False`, same as `cpf`/`rg` — neither field has a
        second column holding an operator's own spelling."""
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"estado_civil": "divorciado", "estado_civil_origem": "manual"},
        )
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(self._com_civil()),
        )
        assert _cliente(scoped, cid)["estado_civil"] == "divorciado"

    @pytest.mark.asyncio
    async def test_a_disagreeing_value_opens_an_admin_conflict_138(self, client, scoped):
        """Migration 138 (owner directive): the old silent skip is now a
        `cliente_campo_conflitos` row — the human value still prevails
        (previous test) AND the disagreement is now recorded for an admin,
        with the prior value preserved as the way back."""
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"estado_civil": "divorciado", "estado_civil_origem": "manual"},
        )
        resultado = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(self._com_civil()),
        )

        assert resultado["conflitos_abertos"] == ["estado_civil"]
        conflitos = scoped.table("cliente_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 1
        conflito = conflitos[0]
        assert conflito["campo"] == "estado_civil"
        assert conflito["valor_anterior"] == "divorciado"
        assert conflito["origem_anterior"] == "manual"
        assert conflito["valor_proposto"] == "casado"
        assert conflito["origem_proposto"] == "certidao_casamento"
        assert conflito["status"] == "pendente"

        # A second read of the SAME disagreement does not pile up a second
        # pending conflict (the partial UNIQUE index's own job, mirrored
        # here in the pre-check).
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(self._com_civil()),
        )
        assert len(scoped.table("cliente_campo_conflitos").select("*").execute().data) == 1

    def test_resolver_conflito_accept_overwrites_and_keeps_the_way_back(self, scoped):
        cid, _did = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, estado_civil="divorciado", estado_civil_origem="manual",
        )])
        conflito_id = str(uuid4())
        scoped.set_table_data("cliente_campo_conflitos", [{
            "id": conflito_id, "org_id": ORG_ID, "cliente_id": cid,
            "campo": "estado_civil",
            "valor_anterior": "divorciado", "origem_anterior": "manual",
            "valor_proposto": "casado", "origem_proposto": "certidao_casamento",
            "confianca_proposta": "alta",
            "fonte_tabela": "cliente_documentos", "fonte_id": str(uuid4()),
            "status": "pendente", "notificado_em": None,
            "decidido_por": None, "decidido_em": None,
        }])
        admin_id = str(uuid4())

        resp = svc.resolver_conflito(
            scoped, ORG_UUID, UUID(conflito_id), aceitar=True, decidido_por=UUID(admin_id)
        )

        assert resp["status"] == "aceito"
        assert resp["decidido_por"] == admin_id
        assert resp["valor_anterior"] == "divorciado"  # the way back, untouched
        cliente = _cliente(scoped, cid)
        assert cliente["estado_civil"] == "casado"
        assert cliente["estado_civil_origem"] == "certidao_casamento"
        assert cliente["estado_civil_confirmado_por"] == admin_id

    def test_resolver_conflito_reject_leaves_the_cliente_untouched(self, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, estado_civil="divorciado", estado_civil_origem="manual",
        )])
        conflito_id = str(uuid4())
        scoped.set_table_data("cliente_campo_conflitos", [{
            "id": conflito_id, "org_id": ORG_ID, "cliente_id": cid,
            "campo": "estado_civil",
            "valor_anterior": "divorciado", "origem_anterior": "manual",
            "valor_proposto": "casado", "origem_proposto": "certidao_casamento",
            "confianca_proposta": "alta",
            "fonte_tabela": "cliente_documentos", "fonte_id": str(uuid4()),
            "status": "pendente", "notificado_em": None,
            "decidido_por": None, "decidido_em": None,
        }])

        resp = svc.resolver_conflito(
            scoped, ORG_UUID, UUID(conflito_id), aceitar=False, decidido_por=UUID(str(uuid4()))
        )

        assert resp["status"] == "rejeitado"
        assert _cliente(scoped, cid)["estado_civil"] == "divorciado"

    def test_resolver_conflito_is_idempotent_first_decision_wins(self, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, estado_civil="divorciado", estado_civil_origem="manual",
        )])
        conflito_id = str(uuid4())
        scoped.set_table_data("cliente_campo_conflitos", [{
            "id": conflito_id, "org_id": ORG_ID, "cliente_id": cid,
            "campo": "estado_civil",
            "valor_anterior": "divorciado", "origem_anterior": "manual",
            "valor_proposto": "casado", "origem_proposto": "certidao_casamento",
            "confianca_proposta": "alta",
            "fonte_tabela": "cliente_documentos", "fonte_id": str(uuid4()),
            "status": "pendente", "notificado_em": None,
            "decidido_por": None, "decidido_em": None,
        }])

        svc.resolver_conflito(
            scoped, ORG_UUID, UUID(conflito_id), aceitar=True, decidido_por=UUID(str(uuid4()))
        )
        with pytest.raises(ValidationError_):
            svc.resolver_conflito(
                scoped, ORG_UUID, UUID(conflito_id), aceitar=False, decidido_por=UUID(str(uuid4()))
            )
        # The FIRST decision's write stands — a rejected second attempt
        # never flips estado_civil back.
        assert _cliente(scoped, cid)["estado_civil"] == "casado"

    @pytest.mark.asyncio
    async def test_a_pending_suggestion_rides_the_extras_surface(self, client, scoped):
        """Deliberately NOT a `documento_checklist_service.ITENS` entry (see
        migration 110's header) — so it surfaces exactly where `nome_oficial`
        already does: `sugestoes_extras` on the checklist GET."""
        from app.modules.card_hub import documento_checklist_service as checklist_svc

        # Human-cleared fields (`origem='manual'`, empty): D1 leaves the
        # reading as a suggestion instead of refilling what a person cleared.
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"estado_civil_origem": "manual", "regime_bens_origem": "manual"},
        )
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(
                self._com_civil(ExtractionConfidence.BAIXA)
            ),
        )
        body = checklist_svc.listar(scoped, ORG_UUID, UUID(cid))
        assert "estado_civil" not in {i["key"] for i in body["items"]}
        assert body["sugestoes_extras"]["estado_civil"]["valor"] == "casado"
        assert body["sugestoes_extras"]["regime_bens"]["valor"] == "comunhao_parcial"


class TestRgIgualCpfEhAplicado:
    """🔴 [2026-09-22] `rg.is_same_as_cpf` == True is APPLIED, not declined.

    A qualificação form putting the CPF into the RG box verbatim used to be
    treated as always a copy-paste bug — but the new Carteira de Identidade
    Nacional (CIN) uses the CPF number as the identity number by design
    (see `rg.is_same_as_cpf`'s own docstring for the contract-08 citation),
    so the collision is frequently the correct reading, not a mistake. The
    contract-generation gate is where a human still gets a chance to look at
    it — as a warning, never a block (`derivacao._partes`).
    """

    @staticmethod
    def _rg_igual_ao_cpf(cpf: str) -> IdentityFields:
        return IdentityFields(
            rg=cpf,
            rg_confianca=ExtractionConfidence.ALTA,
            rg_rotulo="RG",
            source=TextSource.TEXT_LAYER,
        )

    @pytest.mark.asyncio
    async def test_applied_against_an_existing_cpf(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="rg", cliente={"cpf": "412.954.238-98"}
        )
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(self._rg_igual_ao_cpf("412.954.238-98")),
        )
        assert out["aplicado_ao_cliente"]["rg"] is True
        assert _cliente(scoped, cid)["rg"] == "412.954.238-98"
        assert _documento(scoped, did)["extracao_rg"] == "412.954.238-98"

    @pytest.mark.asyncio
    async def test_applied_against_a_cpf_applied_earlier_in_the_same_read(
        self, client, scoped
    ):
        """`cpf` sorts before `rg` in `CAMPOS`, so a document reading BOTH
        fields at once applies `rg` even against the CPF it JUST wrote, not
        only against whatever was already on file."""
        cid, did, storage = await _setup(scoped, tipo="rg")
        fields = IdentityFields(
            cpf="412.954.238-98",
            cpf_confianca=ExtractionConfidence.ALTA,
            rg="412.954.238-98",
            rg_confianca=ExtractionConfidence.ALTA,
            source=TextSource.TEXT_LAYER,
        )
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(fields),
        )
        assert out["aplicado_ao_cliente"]["cpf"] is True
        assert out["aplicado_ao_cliente"]["rg"] is True
        assert _cliente(scoped, cid)["cpf"] == "412.954.238-98"
        assert _cliente(scoped, cid)["rg"] == "412.954.238-98"

    @pytest.mark.asyncio
    async def test_no_longer_pending_once_applied(self, client, scoped):
        """Since the unattended apply now lands the value, it is no longer a
        pending suggestion — `sugestoes_pendentes` only offers a
        first-writer-wins field (`rg`) when the column is still empty."""
        cid, did, storage = await _setup(
            scoped, tipo="rg", cliente={"cpf": "412.954.238-98"}
        )
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(self._rg_igual_ao_cpf("412.954.238-98")),
        )
        sugestoes = svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))
        assert "rg" not in sugestoes

    def test_confirmar_sugestao_accepts_the_same_collision(self, client, scoped):
        """A human explicitly confirming must not be refused a case the
        unattended apply itself would already have landed."""
        cid, did = str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "clientes", [cliente_row(cid, cpf="412.954.238-98", rg=None)]
        )
        scoped.set_table_data("cliente_documentos", [{
            "id": did, "org_id": ORG_ID, "cliente_id": cid,
            "tipo_documento": "rg", "deleted_at": None,
            "extracao_descartada_em": None,
            "extracao_rg": "412.954.238-98",
        }])
        resultado = svc.confirmar_sugestao(
            scoped, ORG_UUID, UUID(cid), UUID(did), item_key="rg",
        )
        assert resultado["confirmado"] is True
        assert _cliente(scoped, cid)["rg"] == "412.954.238-98"


class TestDataCasamentoIsExtracted:
    """Migration 117 (contract F6). `data_casamento` is a `CAMPOS` entry on
    exactly the same terms `estado_civil`/`regime_bens` arrived on —
    `TestEstadoCivilERegimeBensSaoExtraidos`'s own claim, now for the field
    `civil_status.py`'s docstring predicted."""

    @staticmethod
    def _com_casamento(
        confianca=ExtractionConfidence.ALTA, value=date(2010, 3, 12)
    ) -> IdentityFields:
        return IdentityFields(
            data_casamento=value,
            data_casamento_confianca=confianca,
            data_casamento_rotulo="CASARAM-SE EM",
            source=TextSource.TEXT_LAYER,
        )

    @pytest.mark.asyncio
    async def test_a_confident_read_fills_the_column_and_stamps_provenance(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(self._com_casamento()),
        )
        assert out["aplicado_ao_cliente"]["data_casamento"] is True

        row = _cliente(scoped, cid)
        assert row["data_casamento"] == "2010-03-12"
        assert row["data_casamento_origem"] == "certidao_casamento"
        assert row["data_casamento_documento_id"] == did

    @pytest.mark.asyncio
    async def test_a_low_confidence_read_fills_an_empty_field_machine_pending(
        self, client, scoped
    ):
        """D1 (migration 153)."""
        cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(
                self._com_casamento(ExtractionConfidence.BAIXA)
            ),
        )
        row = _cliente(scoped, cid)
        assert row["data_casamento"] == "2010-03-12"
        assert row.get("data_casamento_confirmado_em") is None
        assert _documento(scoped, did)["extracao_data_casamento"] == "2010-03-12"

    @pytest.mark.asyncio
    async def test_an_existing_value_is_not_overwritten(self, client, scoped):
        """`sobrescreve=False`, same reasoning `data_nascimento` gives: "a
        date is a date", no registration-vs-document tension to preserve."""
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={
                "data_casamento": "1999-06-05",
                "data_casamento_origem": "manual",
            },
        )
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(self._com_casamento()),
        )
        assert _cliente(scoped, cid)["data_casamento"] == "1999-06-05"


class TestNacionalidadeIsExtracted:
    """Migration 146 — resolves NOC-REMEDIATE[nacionalidade-identity-parser].
    `nacionalidade` is a `CAMPOS` entry on exactly the same terms
    `genero`/`estado_civil` arrived on (`sobrescreve=False`): a REGISTRATION
    field, first-writer-wins."""

    @staticmethod
    def _com_nacionalidade(
        confianca=ExtractionConfidence.ALTA, value="brasileiro"
    ) -> IdentityFields:
        return IdentityFields(
            nacionalidade=value,
            nacionalidade_confianca=confianca,
            nacionalidade_rotulo="NACIONALIDADE",
            source=TextSource.TEXT_LAYER,
        )

    @pytest.mark.asyncio
    async def test_a_confident_read_fills_the_column_and_stamps_provenance(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped, tipo="cnh")
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(self._com_nacionalidade()),
        )
        assert out["aplicado_ao_cliente"]["nacionalidade"] is True

        row = _cliente(scoped, cid)
        assert row["nacionalidade"] == "brasileiro"
        assert row["nacionalidade_origem"] == "cnh"
        assert row["nacionalidade_documento_id"] == did

    @pytest.mark.asyncio
    async def test_a_low_confidence_read_fills_an_empty_field_machine_pending(
        self, client, scoped
    ):
        """D1 (migration 153)."""
        cid, did, storage = await _setup(scoped, tipo="cnh")
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(
                self._com_nacionalidade(ExtractionConfidence.BAIXA)
            ),
        )
        assert _cliente(scoped, cid)["nacionalidade"] == "brasileiro"
        assert _cliente(scoped, cid).get("nacionalidade_confirmado_em") is None
        assert _documento(scoped, did)["extracao_nacionalidade"] == "brasileiro"

    @pytest.mark.asyncio
    async def test_an_existing_value_is_not_overwritten(self, client, scoped):
        """`sobrescreve=False` — no second column holds an operator's own
        spelling, so a typed value must outrank a later document reading."""
        cid, did, storage = await _setup(
            scoped, tipo="cnh",
            cliente={
                "nacionalidade": "italiano",
                "nacionalidade_origem": "manual",
            },
        )
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(self._com_nacionalidade()),
        )
        assert _cliente(scoped, cid)["nacionalidade"] == "italiano"


class TestDataEmissaoRidesTheDocumentNotTheClient:
    """Migration 117. `data_emissao` is deliberately NOT a `CAMPOS` entry —
    it never reaches `clientes`, only `cliente_documentos`."""

    @pytest.mark.asyncio
    async def test_recorded_on_the_document_regardless_of_confidence(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
        fields = IdentityFields(
            data_emissao=date(2024, 3, 15),
            data_emissao_confianca=ExtractionConfidence.ALTA,
            data_emissao_rotulo="EMITIDA EM",
            source=TextSource.TEXT_LAYER,
        )
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(fields),
        )
        assert out["status"] == "ok"
        doc = _documento(scoped, did)
        assert doc["extracao_data_emissao"] == "2024-03-15"
        assert doc["extracao_data_emissao_confianca"] == "alta"
        assert doc["extracao_data_emissao_rotulo"] == "EMITIDA EM"
        # Never promoted — there is no clientes.data_emissao column at all.
        assert "data_emissao" not in _cliente(scoped, cid)

    @pytest.mark.asyncio
    async def test_a_document_carrying_only_data_emissao_is_not_sem_dados(
        self, client, scoped
    ):
        """`achou_algo` must count `data_emissao` too — a document that
        found nothing else still found something."""
        cid, did, storage = await _setup(scoped, tipo="certidao_nascimento")
        fields = IdentityFields(
            data_emissao=date(2024, 3, 15),
            data_emissao_confianca=ExtractionConfidence.BAIXA,
            data_emissao_rotulo="FECHAMENTO_CARTORIO",
            source=TextSource.OCR,
        )
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(fields),
        )
        assert out["status"] == "ok"


class TestCertidaoEstadoCivilMaisRecente:
    """`certidao_estado_civil_mais_recente` — the office's 90-day-freshness
    rule reads the DOCUMENT, not the client."""

    @pytest.mark.asyncio
    async def test_none_when_no_qualifying_document_has_an_emission_date(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
        assert svc.certidao_estado_civil_mais_recente(
            scoped, ORG_UUID, UUID(cid)
        ) is None

    @pytest.mark.asyncio
    async def test_returns_the_newest_emission_across_both_certidao_types(
        self, client, scoped
    ):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        antigo, novo = str(uuid4()), str(uuid4())
        scoped.set_table_data("cliente_documentos", [
            {
                "id": antigo, "org_id": ORG_ID, "cliente_id": cid,
                "tipo_documento": "certidao_nascimento", "deleted_at": None,
                "extracao_descartada_em": None,
                "extracao_data_emissao": "2020-01-10",
            },
            {
                "id": novo, "org_id": ORG_ID, "cliente_id": cid,
                "tipo_documento": "certidao_casamento", "deleted_at": None,
                "extracao_descartada_em": None,
                "extracao_data_emissao": "2024-03-15",
            },
        ])
        out = svc.certidao_estado_civil_mais_recente(scoped, ORG_UUID, UUID(cid))
        assert out is not None
        assert out["documento_id"] == novo
        assert out["emitida_em"] == "2024-03-15"
        assert isinstance(out["dias"], int)
        assert out["dias"] >= 0

    @pytest.mark.asyncio
    async def test_excludes_deleted_and_discarded_documents(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        deletado, descartado = str(uuid4()), str(uuid4())
        scoped.set_table_data("cliente_documentos", [
            {
                "id": deletado, "org_id": ORG_ID, "cliente_id": cid,
                "tipo_documento": "certidao_casamento",
                "deleted_at": "2026-01-01T00:00:00+00:00",
                "extracao_descartada_em": None,
                "extracao_data_emissao": "2025-01-01",
            },
            {
                "id": descartado, "org_id": ORG_ID, "cliente_id": cid,
                "tipo_documento": "certidao_casamento", "deleted_at": None,
                "extracao_descartada_em": "2026-01-01T00:00:00+00:00",
                "extracao_data_emissao": "2025-06-01",
            },
        ])
        assert svc.certidao_estado_civil_mais_recente(
            scoped, ORG_UUID, UUID(cid)
        ) is None

    @pytest.mark.asyncio
    async def test_the_manual_date_alone_is_reported_with_no_documento_id(
        self, client, scoped
    ):
        """Migration 148 — a certidão nobody has uploaded, only typed in."""
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [cliente_row(cid, certidao_estado_civil_emitida_em="2025-02-20")],
        )
        scoped.set_table_data("cliente_documentos", [])
        out = svc.certidao_estado_civil_mais_recente(scoped, ORG_UUID, UUID(cid))
        assert out is not None
        assert out["documento_id"] is None
        assert out["emitida_em"] == "2025-02-20"

    @pytest.mark.asyncio
    async def test_the_more_recent_of_manual_and_document_wins(self, client, scoped):
        """The SAME 'freshest reading wins' comparison already run across
        multiple uploaded certidões, extended to a manually-typed one."""
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [cliente_row(cid, certidao_estado_civil_emitida_em="2026-01-01")],
        )
        antigo = str(uuid4())
        scoped.set_table_data("cliente_documentos", [
            {
                "id": antigo, "org_id": ORG_ID, "cliente_id": cid,
                "tipo_documento": "certidao_casamento", "deleted_at": None,
                "extracao_descartada_em": None,
                "extracao_data_emissao": "2020-01-10",
            },
        ])
        out = svc.certidao_estado_civil_mais_recente(scoped, ORG_UUID, UUID(cid))
        assert out is not None
        assert out["documento_id"] is None
        assert out["emitida_em"] == "2026-01-01"

    @pytest.mark.asyncio
    async def test_a_fresher_uploaded_document_wins_over_an_older_manual_date(
        self, client, scoped
    ):
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [cliente_row(cid, certidao_estado_civil_emitida_em="2018-05-05")],
        )
        novo = str(uuid4())
        scoped.set_table_data("cliente_documentos", [
            {
                "id": novo, "org_id": ORG_ID, "cliente_id": cid,
                "tipo_documento": "certidao_casamento", "deleted_at": None,
                "extracao_descartada_em": None,
                "extracao_data_emissao": "2024-03-15",
            },
        ])
        out = svc.certidao_estado_civil_mais_recente(scoped, ORG_UUID, UUID(cid))
        assert out is not None
        assert out["documento_id"] == novo
        assert out["emitida_em"] == "2024-03-15"


# ─── End-to-end through the REAL ladder (B5 — the wiring this slice finishes) ──
#
# Every test above scripts `FakeIdentityExtractor` — proof that THIS service's
# apply/suggest/confirm/access-log code is correct, but not that the seed's
# own parser wiring (`real.LadderIdentityExtractor`) actually produces the
# values this service consumes. `civil_status.find_data_casamento`/
# `find_data_emissao` shipped without that wiring in an earlier commit on
# this same branch (the deviation the "no incomplete commits" rule caught);
# this section is the fix, mirroring `test_civil_status.py`'s own
# `TestCivilStatusWiring` pattern — a stubbed resolver stands in for the
# vision rung, so still no patch of our own code and no real vision call.

CERTIDAO_CASAMENTO_COM_EMISSAO = (
    "CERTIDAO DE CASAMENTO\n"
    "OS CONTRAENTES CASARAM-SE EM DOZE DE MARCO DE DOIS MIL E DEZ SOB O "
    "REGIME DA COMUNHAO PARCIAL DE BENS\n"
    "EMITIDA EM 15 DE MARCO DE 2024\n"
)


class _StubResolved:
    def __init__(self, text="", error=None, error_message=None):
        self.text, self.error, self.error_message = text, error, error_message


class _StubResolver:
    """Stands in for the media resolver's vision rung — dependency
    injection, not a patch of our own code."""

    def __init__(self, resolved=None):
        self._resolved = resolved or _StubResolved(text="")
        self.calls = 0

    async def resolve(self, media):
        self.calls += 1
        return self._resolved


class TestDataCasamentoEDataEmissaoViaLadderReal:
    @pytest.mark.asyncio
    async def test_a_real_certidao_read_stores_both_dates_end_to_end(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
        resolver = _StubResolver(_StubResolved(text=CERTIDAO_CASAMENTO_COM_EMISSAO))
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=LadderIdentityExtractor(resolver=resolver, max_pages=None),
        )
        assert out["status"] == "ok"
        assert out["aplicado_ao_cliente"]["data_casamento"] is True

        row = _cliente(scoped, cid)
        assert row["data_casamento"] == "2010-03-12"
        assert row["data_casamento_origem"] == "certidao_casamento"

        doc = _documento(scoped, did)
        assert doc["extracao_data_casamento"] == "2010-03-12"
        assert doc["extracao_data_emissao"] == "2024-03-15"
        assert doc["extracao_data_emissao_confianca"] == "alta"
        assert doc["extracao_data_emissao_rotulo"] == "EMITIDA EM"
        # Never promoted — no clientes.data_emissao column exists at all.
        assert "data_emissao" not in row

        info = svc.certidao_estado_civil_mais_recente(scoped, ORG_UUID, UUID(cid))
        assert info is not None
        assert info["documento_id"] == did
        assert info["emitida_em"] == "2024-03-15"

    @pytest.mark.asyncio
    async def test_a_real_certidao_with_no_explicit_emissao_label_falls_back_low_confidence(
        self, client, scoped
    ):
        """The closing-line heuristic still reaches the document row —
        typed `baixa`, never promoted (data_emissao is not a CAMPO), but
        recorded all the same."""
        cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
        texto = (
            "CERTIDAO DE CASAMENTO\n"
            "OS CONTRAENTES CASARAM-SE EM 12/03/2010 SOB O REGIME DA "
            "COMUNHAO PARCIAL DE BENS\n"
            "SAO PAULO, DOZE DE MARCO DE DOIS MIL E VINTE E QUATRO.\n"
        )
        resolver = _StubResolver(_StubResolved(text=texto))
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=LadderIdentityExtractor(resolver=resolver, max_pages=None),
        )
        doc = _documento(scoped, did)
        assert doc["extracao_data_emissao"] == "2024-03-12"
        assert doc["extracao_data_emissao_confianca"] == "baixa"
        assert doc["extracao_data_emissao_rotulo"] == "FECHAMENTO_CARTORIO"


class TestNacionalidadeViaLadderReal:
    """Migration 146, wired end to end — the certidão fixture two spouses of
    the SAME nationality, each printed in their own grammatical gender,
    resolving through the seed's real parser + this service's storage."""

    @pytest.mark.asyncio
    async def test_a_real_certidao_naming_two_same_nationality_spouses(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
        texto = (
            "CERTIDAO DE CASAMENTO\n"
            "ALMIR TEIXEIRA DA COSTA, de nacionalidade brasileira, filho de "
            "PEDRO TEIXEIRA DA COSTA.\n"
            "MARIANA PELLEGRINI RANGEL, de nacionalidade brasileira, filha "
            "de EMILIO RANGEL.\n"
        )
        resolver = _StubResolver(_StubResolved(text=texto))
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=LadderIdentityExtractor(resolver=resolver, max_pages=None),
        )
        assert out["aplicado_ao_cliente"]["nacionalidade"] is True
        assert _cliente(scoped, cid)["nacionalidade"] == "brasileiro"


class TestACertidaoOfTwoSpousesStillFeedsTheCard:
    """A certidão de casamento names two people. The card knows which one it
    belongs to (the titular hint), and a result that could not pick a spouse
    is a NOTICE — the couple-level facts on it must still reach the card."""

    @pytest.mark.asyncio
    async def test_the_card_holder_is_passed_as_the_titular_hint(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"nome": "REGINA TESTE", "cpf": "041.333.248-97"},
        )
        fake = FakeIdentityExtractor(_alta())
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did), extractor=fake,
        )
        assert len(fake.titulares) == 1
        assert fake.titulares[0].cpf == "041.333.248-97"
        assert fake.titulares[0].nome == "REGINA TESTE"

    @pytest.mark.asyncio
    async def test_an_aviso_does_not_discard_the_estado_civil(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
        resultado = IdentityFields(
            estado_civil="divorciado",
            estado_civil_confianca=ExtractionConfidence.ALTA,
            estado_civil_rotulo="AVERBACAO",
            source=TextSource.OCR,
            aviso="titulares_multiplos",
            aviso_mensagem="nome (2 titulares), cpf (2 titulares)",
        )
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(resultado),
        )
        assert out["status"] != "erro"
        d = _documento(scoped, did)
        assert d["extracao_status"] == "ok"
        assert d["extracao_estado_civil"] == "divorciado"
