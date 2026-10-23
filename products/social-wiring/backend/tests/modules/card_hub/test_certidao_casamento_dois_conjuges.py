"""A certidão de casamento read for BOTH spouses (deal 857, prod, 2026-10-21).

The SP Registro Civil standard prints the couple's names, CPFs, birthdates,
nationalities and the RGs (cadastro annotation). Applying it must:

- fill the titular's EMPTY birthdate / nationality and the couple's facts;
- fill the other spouse — already linked as cônjuge on the card — with HER
  facts (never duplicating a person; creating one is covered in
  `test_certidao_casamento_conjuge_completo.py`);
- when the other spouse was not attributed (a single-entry read), still hand
  her the COUPLE's facts (estado civil, regime, data do casamento);
- never overwrite a manual value silently — a differing value opens a review;
- each spouse's RG from the cadastro annotation fills an EMPTY field (owner
  decision 2026-10-21, supersedes the 2026-10-13 "not an RG source" rule).

Invented names; synthetic check-digit-valid CPFs.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import identidade_extracao_service as svc
from app.services.conjuge_vinculo import vincular_conjuge
from noctusai_lib.integrations.documents import ExtractionConfidence, FakeIdentityExtractor, IdentityFields, TextSource
from noctusai_lib.integrations.documents.conjuges import ConjugeLido

from tests.modules.card_hub.test_identidade_extracao import ORG_UUID, _cliente, _documento, _setup
from tests.modules.card_hub.conftest import cliente_row  # noqa: F401

RAFAEL_CPF = "529.982.247-25"
BEATRIZ_CPF = "111.444.777-35"


def _leitura(*, com_a_outra: bool = True) -> IdentityFields:
    eu = ConjugeLido(
        nome="BEATRIZ ALENCAR QUINTANA", cpf=BEATRIZ_CPF, cpf_confianca="alta",
        data_nascimento=date(1990, 6, 4), data_nascimento_confianca="media",
        nacionalidade="brasileiro", nacionalidade_confianca="media",
        rg="55.666.777-X", rg_orgao="SSP/SP", rg_confianca="media", titular=True,
    )
    outro = ConjugeLido(
        nome="RAFAEL MENEZES DO PRADO", cpf=RAFAEL_CPF, cpf_confianca="alta",
        data_nascimento=date(1985, 3, 10), data_nascimento_confianca="media",
        nacionalidade="brasileiro", nacionalidade_confianca="media",
        rg="11.222.333-4", rg_orgao="SSP/SP", rg_confianca="media",
    )
    return IdentityFields(
        nome="BEATRIZ ALENCAR QUINTANA", nome_confianca=ExtractionConfidence.MEDIA,
        data_nascimento=eu.data_nascimento,
        data_nascimento_confianca=ExtractionConfidence.MEDIA,
        rg=eu.rg, rg_confianca=ExtractionConfidence.MEDIA,
        rg_orgao=eu.rg_orgao, rg_orgao_confianca=ExtractionConfidence.MEDIA,
        nacionalidade="brasileiro", nacionalidade_confianca=ExtractionConfidence.MEDIA,
        estado_civil="casado", estado_civil_confianca=ExtractionConfidence.ALTA,
        regime_bens="comunhao_parcial", regime_bens_confianca=ExtractionConfidence.ALTA,
        data_casamento=date(2020, 4, 12), data_casamento_confianca=ExtractionConfidence.ALTA,
        source=TextSource.OCR,
        conjuges=(outro, eu) if com_a_outra else (eu,),
    )


async def _casal(scoped, **extra_outro):
    cid, did, storage = await _setup(
        scoped, tipo="certidao_casamento",
        cliente={"nome": "BEATRIZ ALENCAR QUINTANA", "cpf": None},
    )
    outro_id = str(uuid4())
    linha = cliente_row(outro_id, nome="RAFAEL MENEZES DO PRADO", **extra_outro)
    scoped.set_table_data(
        "clientes", scoped.table("clientes").select("*").execute().data + [linha]
    )
    scoped.table("clientes").update({"conjuge_cliente_id": outro_id}).eq("id", cid).execute()
    scoped.table("clientes").update({"conjuge_cliente_id": cid}).eq("id", outro_id).execute()
    return cid, did, outro_id, storage


class TestAmbosOsConjuges:
    @pytest.mark.asyncio
    async def test_titular_empty_fields_are_filled_from_the_certidao(self, client, scoped):
        cid, did, _outro, storage = await _casal(scoped)
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura()),
        )
        c = _cliente(scoped, cid)
        assert c["data_nascimento"] == "1990-06-04"
        assert c["data_nascimento_origem"] == "certidao_casamento"
        assert c["nacionalidade"] == "brasileiro"
        assert c["estado_civil"] == "casado"
        # The titular's own RG/órgão off the cadastro annotation fills the
        # EMPTY field, machine-pending (owner decision 2026-10-21).
        assert c["rg"] == "55.666.777-X" and c["rg_orgao_expedidor"] == "SSP/SP"
        assert c["rg_origem"] == "certidao_casamento" and not c.get("rg_confirmado_em")

    @pytest.mark.asyncio
    async def test_the_linked_spouse_gets_her_own_and_the_couples_facts(self, client, scoped):
        cid, did, outro_id, storage = await _casal(scoped)
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura()),
        )
        o = _cliente(scoped, outro_id)
        assert o["cpf"] == RAFAEL_CPF
        assert o["data_nascimento"] == "1985-03-10"
        assert o["nacionalidade"] == "brasileiro"
        for campo in ("estado_civil", "regime_bens", "data_casamento", "data_nascimento"):
            assert o[f"{campo}_origem"] == "certidao_casamento", campo
        assert o["estado_civil"] == "casado" and o["regime_bens"] == "comunhao_parcial"
        # Nobody was created: the two clientes that existed are the only ones.
        assert len(scoped.table("clientes").select("*").execute().data) == 2

    @pytest.mark.asyncio
    async def test_each_entry_records_the_rg_the_page_prints_and_the_spouse_gets_it(
        self, client, scoped
    ):
        cid, did, outro_id, storage = await _casal(scoped)
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura()),
        )
        entradas = {e["nome"]: e for e in _documento(scoped, did)["extracao_conjuges"]}
        assert entradas["RAFAEL MENEZES DO PRADO"]["rg"] == "11.222.333-4"
        assert entradas["BEATRIZ ALENCAR QUINTANA"]["rg_orgao"] == "SSP/SP"
        assert entradas["RAFAEL MENEZES DO PRADO"]["cliente_id"] == outro_id
        o = _cliente(scoped, outro_id)
        assert o["rg"] == "11.222.333-4" and o["rg_orgao_expedidor"] == "SSP/SP"
        assert o["rg_origem"] == "certidao_casamento" and not o.get("rg_confirmado_em")

    @pytest.mark.asyncio
    async def test_a_manual_value_on_the_spouse_is_never_overwritten(self, client, scoped):
        cid, did, outro_id, storage = await _casal(
            scoped,
            regime_bens="separacao_total", regime_bens_origem="manual",
        )
        scoped.set_table_data("cliente_campo_conflitos", [])
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura()),
        )
        o = _cliente(scoped, outro_id)
        assert o["regime_bens"] == "separacao_total"
        pendentes = [
            r for r in scoped.table("cliente_campo_conflitos").select("*").execute().data
            if r.get("status") == "pendente" and r.get("cliente_id") == outro_id
        ]
        assert [r["campo"] for r in pendentes] == ["regime_bens"]


class TestConjugeSemEntradaRecebeOsFatosDoCasal:
    @pytest.mark.asyncio
    async def test_already_linked_spouse_gets_the_couples_facts_on_a_single_entry_read(
        self, client, scoped
    ):
        cid, did, outro_id, storage = await _casal(scoped)
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura(com_a_outra=False)),
        )
        o = _cliente(scoped, outro_id)
        assert o["estado_civil"] == "casado"
        assert o["regime_bens"] == "comunhao_parcial"
        assert o["data_casamento"] == "2020-04-12"
        assert o["estado_civil_origem"] == "certidao_casamento"
        assert o["estado_civil_documento_id"] == did
        # Per-person facts are NOT guessed for her.
        assert not o.get("cpf") and not o.get("data_nascimento")

    @pytest.mark.asyncio
    async def test_a_spouse_added_later_gets_them_when_the_link_is_written(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"nome": "BEATRIZ ALENCAR QUINTANA", "cpf": None},
        )
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura(com_a_outra=False)),
        )
        # Marked ok by the extraction; now "Adicionar cônjuge" by hand.
        assert _documento(scoped, did)["extracao_status"] == "ok"
        outro_id = str(uuid4())
        scoped.set_table_data(
            "clientes",
            scoped.table("clientes").select("*").execute().data
            + [cliente_row(outro_id, nome="Fulano Qualquer")],
        )
        vincular_conjuge(scoped, str(ORG_UUID), outro_id, cid)
        o = _cliente(scoped, outro_id)
        assert o["estado_civil"] == "casado"
        assert o["regime_bens"] == "comunhao_parcial"
        assert o["data_casamento"] == "2020-04-12"
        assert o["data_casamento_origem"] == "certidao_casamento"

    @pytest.mark.asyncio
    async def test_a_unlinked_cliente_is_never_given_the_couples_facts(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"nome": "BEATRIZ ALENCAR QUINTANA", "cpf": None},
        )
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura(com_a_outra=False)),
        )
        estranho = str(uuid4())
        scoped.set_table_data(
            "clientes",
            scoped.table("clientes").select("*").execute().data + [cliente_row(estranho)],
        )
        assert svc._aplicar_fatos_do_casal(
            scoped, ORG_UUID, _documento(scoped, did), UUID(cid), UUID(estranho)
        ) == []
        assert not _cliente(scoped, estranho).get("estado_civil")


class TestConjugeHerdaOEstadoCivilDoCasal:
    """Item 5 — when the certidão links A and B, B gets what A got (estado
    civil / regime / data), however A's own value arrived."""

    @pytest.mark.asyncio
    async def test_a_value_already_on_file_for_the_titular_still_reaches_the_spouse(
        self, client, scoped
    ):
        # A's estado civil is already 'casado' (typed by the operator, so its
        # origin is NOT the certidão) and the certidão agrees with it.
        cid, did, outro_id, storage = await _casal(scoped)
        scoped.table("clientes").update(
            {"estado_civil": "casado", "estado_civil_origem": "manual"}
        ).eq("id", cid).execute()
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura(com_a_outra=False)),
        )
        o = _cliente(scoped, outro_id)
        assert o["estado_civil"] == "casado"
        assert o["regime_bens"] == "comunhao_parcial"
        assert o["data_casamento"] == "2020-04-12"

    @pytest.mark.asyncio
    async def test_a_spouse_entry_that_does_not_match_the_linked_name_still_gets_the_couples_facts(
        self, client, scoped
    ):
        # The certidão prints the husband under a name the card does not carry
        # (a nickname on the card): the per-person entry is not applied, the
        # COUPLE's facts are — the card's own link says they share the marriage.
        cid, did, outro_id, storage = await _casal(scoped)
        scoped.table("clientes").update({"nome": "Fulano Qualquer"}).eq("id", outro_id).execute()
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura()),
        )
        o = _cliente(scoped, outro_id)
        assert o["estado_civil"] == "casado"
        assert o["regime_bens"] == "comunhao_parcial"
        assert o["data_casamento"] == "2020-04-12"

    @pytest.mark.asyncio
    async def test_a_titular_who_disagrees_with_the_certidao_gives_the_spouse_nothing(
        self, client, scoped
    ):
        cid, did, outro_id, storage = await _casal(scoped)
        scoped.table("clientes").update(
            {"estado_civil": "divorciado", "estado_civil_origem": "manual"}
        ).eq("id", cid).execute()
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura(com_a_outra=False)),
        )
        assert not _cliente(scoped, outro_id).get("estado_civil")
