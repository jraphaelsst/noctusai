"""Owner decisions 2026-10-21 on a certidão de casamento (follows the slice
"certidão de casamento reads both spouses").

1. The OTHER spouse is CREATED when no cliente matches — CPF first (a person
   already in the org is linked, never duplicated), then name within the card;
   only with a CPF that passes its check digits and a name that was read. Created
   through "Adicionar cônjuge" (`compradores_service.adicionar`), fields
   machine-pending with origem `certidao_casamento`.
2. RG / órgão from the certidão fill EMPTY fields only: a different on-file
   value opens the review, a manual correction is protected, nothing is
   overwritten.
3. Filiação (nome_mae / nome_pai) and naturalidade round-trip.

Invented names; synthetic check-digit-valid CPFs.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.integrations.documents import ExtractionConfidence, FakeIdentityExtractor, IdentityFields, TextSource
from noctusai_lib.integrations.documents.conjuges import ConjugeLido

from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_identidade_extracao import ORG_UUID, _cliente, _documento, _setup

RAFAEL_CPF = "529.982.247-25"
BEATRIZ_CPF = "111.444.777-35"
CPF_INVALIDO = "529.982.247-26"


def _leitura(*, cpf_outro: str | None = RAFAEL_CPF, rg_eu: str = "55.666.777-X") -> IdentityFields:
    eu = ConjugeLido(
        nome="BEATRIZ ALENCAR QUINTANA", cpf=BEATRIZ_CPF, cpf_confianca="alta",
        data_nascimento=date(1990, 6, 4), data_nascimento_confianca="media",
        rg=rg_eu, rg_orgao="SSP/SP", rg_confianca="media", rg_orgao_confianca="media",
        nome_pai="Hugo Quintana", nome_pai_confianca="media",
        nome_mae="Lia Alencar", nome_mae_confianca="media",
        naturalidade="Santos/SP", naturalidade_confianca="media", titular=True,
    )
    outro = ConjugeLido(
        nome="RAFAEL MENEZES DO PRADO", cpf=cpf_outro, cpf_confianca="alta",
        data_nascimento=date(1985, 3, 10), data_nascimento_confianca="media",
        rg="11.222.333-4", rg_orgao="SSP/SP", rg_confianca="media", rg_orgao_confianca="media",
        nome_pai="Aurelio Prado", nome_pai_confianca="media",
        nome_mae="Marta Menezes", nome_mae_confianca="media",
        naturalidade="Campinas/SP", naturalidade_confianca="media",
    )
    M = ExtractionConfidence.MEDIA
    return IdentityFields(
        nome="BEATRIZ ALENCAR QUINTANA", nome_confianca=M,
        rg=eu.rg, rg_confianca=M, rg_orgao=eu.rg_orgao, rg_orgao_confianca=M,
        nome_pai=eu.nome_pai, nome_pai_confianca=M,
        nome_mae=eu.nome_mae, nome_mae_confianca=M,
        naturalidade=eu.naturalidade, naturalidade_confianca=M,
        estado_civil="casado", estado_civil_confianca=ExtractionConfidence.ALTA,
        regime_bens="comunhao_parcial", regime_bens_confianca=ExtractionConfidence.ALTA,
        data_casamento=date(2020, 4, 12), data_casamento_confianca=ExtractionConfidence.ALTA,
        source=TextSource.OCR, conjuges=(outro, eu),
    )


async def _cartao(scoped, *, com_atendimento: bool = True, **cliente):
    cid, did, storage = await _setup(
        scoped, tipo="certidao_casamento",
        cliente={"nome": "BEATRIZ ALENCAR QUINTANA", **cliente},
    )
    aid = str(uuid4())
    scoped.set_table_data("atendimentos", [{
        "id": aid, "org_id": ORG_ID, "cliente_id": cid, "lead_id": None,
        "meta_ads_lead_id": None, "status": "aberta", "substituida_por": None,
        "arquivado": False, "titulo": "Compra", "created_at": "2026-01-01T00:00:00+00:00",
        "closed_at": None,
    }] if com_atendimento else [])
    scoped.set_table_data("atendimento_partes", [])
    return cid, did, storage, aid


async def _ler(scoped, cid, did, storage, leitura):
    return await svc.extrair_identidade(
        scoped, storage, ORG_UUID, UUID(cid), UUID(did),
        extractor=FakeIdentityExtractor(leitura),
    )


def _clientes(scoped) -> list[dict]:
    return scoped.table("clientes").select("*").execute().data


def _outro(scoped, cid) -> dict | None:
    return next((r for r in _clientes(scoped) if r["id"] != cid), None)


class TestCriaOConjugeQueNaoExiste:
    @pytest.mark.asyncio
    async def test_a_valid_cpf_creates_and_links_the_other_spouse(self, client, scoped):
        cid, did, storage, aid = await _cartao(scoped)
        await _ler(scoped, cid, did, storage, _leitura())
        assert len(_clientes(scoped)) == 2
        o = _outro(scoped, cid)
        assert o["nome"] == "RAFAEL MENEZES DO PRADO"
        # Linked both ways, with the certidão as the provenance.
        assert o["conjuge_cliente_id"] == cid and _cliente(scoped, cid)["conjuge_cliente_id"] == o["id"]
        assert o["conjuge_origem"] == "certidao_casamento"
        assert o["conjuge_documento_id"] == did and not o.get("conjuge_confirmado_em")
        # Added as a `conjuge` party of this card's atendimento ("Adicionar cônjuge").
        partes = scoped.table("atendimento_partes").select("*").execute().data
        assert [(p["cliente_id"], p["papel"], p["lado"]) for p in partes] == [
            (o["id"], "conjuge", "comprador")
        ]
        # Fields: origem certidao_casamento, machine-pending (never `manual`).
        assert o["cpf"] == RAFAEL_CPF and o["cpf_origem"] == "certidao_casamento"
        assert o["data_nascimento"] == "1985-03-10"
        assert o["rg"] == "11.222.333-4" and o["rg_orgao_expedidor"] == "SSP/SP"
        for campo in ("cpf", "rg", "nome_mae", "nome_pai", "naturalidade", "estado_civil"):
            assert o[f"{campo}_origem"] == "certidao_casamento", campo
            assert not o.get(f"{campo}_confirmado_em"), campo
        assert (o["nome_pai"], o["nome_mae"], o["naturalidade"]) == (
            "Aurelio Prado", "Marta Menezes", "Campinas/SP",
        )
        entradas = {e["nome"]: e for e in _documento(scoped, did)["extracao_conjuges"]}
        assert entradas["RAFAEL MENEZES DO PRADO"]["cliente_id"] == o["id"]

    @pytest.mark.asyncio
    async def test_an_invalid_cpf_does_not_create(self, client, scoped):
        cid, did, storage, _ = await _cartao(scoped)
        await _ler(scoped, cid, did, storage, _leitura(cpf_outro=CPF_INVALIDO))
        assert len(_clientes(scoped)) == 1
        assert scoped.table("atendimento_partes").select("*").execute().data == []
        entradas = {e["nome"]: e for e in _documento(scoped, did)["extracao_conjuges"]}
        assert entradas["RAFAEL MENEZES DO PRADO"]["cliente_id"] is None  # kept for review

    @pytest.mark.asyncio
    async def test_no_cpf_does_not_create(self, client, scoped):
        cid, did, storage, _ = await _cartao(scoped)
        await _ler(scoped, cid, did, storage, _leitura(cpf_outro=None))
        assert len(_clientes(scoped)) == 1

    @pytest.mark.asyncio
    async def test_an_existing_cpf_holder_in_the_org_is_linked_not_duplicated(self, client, scoped):
        cid, did, storage, _ = await _cartao(scoped)
        existente = str(uuid4())
        scoped.set_table_data(
            "clientes",
            _clientes(scoped) + [cliente_row(
                existente, nome="Rafael Menezes", cpf=RAFAEL_CPF, cpf_origem="manual",
            )],
        )
        await _ler(scoped, cid, did, storage, _leitura())
        assert len(_clientes(scoped)) == 2  # nobody new
        assert _cliente(scoped, cid)["conjuge_cliente_id"] == existente
        assert _cliente(scoped, existente)["conjuge_cliente_id"] == cid
        # Their typed CPF is untouched.
        assert _cliente(scoped, existente)["cpf_origem"] == "manual"

    @pytest.mark.asyncio
    async def test_a_name_match_on_the_card_is_linked_not_duplicated(self, client, scoped):
        cid, did, storage, aid = await _cartao(scoped)
        # Rafael is already a party of the card (no CPF known yet).
        rid = str(uuid4())
        scoped.set_table_data(
            "clientes", _clientes(scoped) + [cliente_row(rid, nome="Rafael Menezes do Prado")]
        )
        scoped.set_table_data("atendimento_partes", [{
            "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid, "cliente_id": rid,
            "lado": "comprador", "papel": "comprador", "ordem": 0,
        }])
        await _ler(scoped, cid, did, storage, _leitura())
        assert len(_clientes(scoped)) == 2
        assert _cliente(scoped, rid)["cpf"] == RAFAEL_CPF

    @pytest.mark.asyncio
    async def test_a_titular_already_married_on_file_to_someone_else_creates_nobody(
        self, client, scoped
    ):
        outra = str(uuid4())
        cid, did, storage, _ = await _cartao(scoped, conjuge_cliente_id=outra)
        scoped.set_table_data(
            "clientes", _clientes(scoped) + [cliente_row(outra, nome="Carla Outra")]
        )
        await _ler(scoped, cid, did, storage, _leitura())
        assert len(_clientes(scoped)) == 2  # still just titular + Carla
        assert _cliente(scoped, cid)["conjuge_cliente_id"] == outra

    @pytest.mark.asyncio
    async def test_without_an_unambiguous_destination_nobody_is_created(self, client, scoped):
        cid, did, storage, _ = await _cartao(scoped, com_atendimento=False)
        await _ler(scoped, cid, did, storage, _leitura())
        assert len(_clientes(scoped)) == 1

    @pytest.mark.asyncio
    async def test_a_compromised_read_creates_nobody(self, client, scoped):
        cid, did, storage, _ = await _cartao(scoped)
        leitura = _leitura()
        from dataclasses import replace

        await _ler(scoped, cid, did, storage, replace(leitura, aviso="leitura_comprometida"))
        assert len(_clientes(scoped)) == 1


class TestRgPreencheVazioNuncaSobrescreve:
    @pytest.mark.asyncio
    async def test_rg_and_orgao_fill_empty_fields(self, client, scoped):
        cid, did, storage, _ = await _cartao(scoped)
        await _ler(scoped, cid, did, storage, _leitura())
        c = _cliente(scoped, cid)
        assert (c["rg"], c["rg_orgao_expedidor"]) == ("55.666.777-X", "SSP/SP")
        assert c["rg_origem"] == "certidao_casamento" and not c.get("rg_confirmado_em")

    @pytest.mark.asyncio
    async def test_a_different_rg_on_file_opens_the_review_and_keeps_the_value(self, client, scoped):
        cid, did, storage, _ = await _cartao(scoped, rg="99.888.777-1", rg_origem="rg")
        scoped.set_table_data("cliente_campo_conflitos", [])
        await _ler(scoped, cid, did, storage, _leitura())
        assert _cliente(scoped, cid)["rg"] == "99.888.777-1"
        pendentes = [
            r for r in scoped.table("cliente_campo_conflitos").select("*").execute().data
            if r.get("status") == "pendente" and r.get("cliente_id") == cid and r["campo"] == "rg"
        ]
        assert len(pendentes) == 1 and pendentes[0]["origem_proposto"] == "certidao_casamento"

    @pytest.mark.asyncio
    async def test_a_manual_correction_is_protected(self, client, scoped):
        cid, did, storage, _ = await _cartao(scoped, rg="99.888.777-1", rg_origem="manual")
        scoped.set_table_data("cliente_campo_conflitos", [])
        await _ler(scoped, cid, did, storage, _leitura())
        assert _cliente(scoped, cid)["rg"] == "99.888.777-1"
        assert _cliente(scoped, cid)["rg_origem"] == "manual"

    @pytest.mark.asyncio
    async def test_the_same_rg_is_a_no_op(self, client, scoped):
        cid, did, storage, _ = await _cartao(scoped, rg="55.666.777-X", rg_origem="rg")
        await _ler(scoped, cid, did, storage, _leitura())
        assert _cliente(scoped, cid)["rg_origem"] == "rg"


class TestFiliacaoENaturalidade:
    @pytest.mark.asyncio
    async def test_round_trip_onto_the_cliente_machine_pending(self, client, scoped):
        cid, did, storage, _ = await _cartao(scoped)
        await _ler(scoped, cid, did, storage, _leitura())
        c = _cliente(scoped, cid)
        assert (c["nome_pai"], c["nome_mae"], c["naturalidade"]) == (
            "Hugo Quintana", "Lia Alencar", "Santos/SP",
        )
        for campo in ("nome_pai", "nome_mae", "naturalidade"):
            assert c[f"{campo}_origem"] == "certidao_casamento"
            assert c[f"{campo}_documento_id"] == did
            assert not c.get(f"{campo}_confirmado_em")
        d = _documento(scoped, did)
        assert d["extracao_nome_pai"] == "Hugo Quintana" and d["extracao_naturalidade"] == "Santos/SP"

    @pytest.mark.asyncio
    async def test_a_different_mother_on_file_is_a_review_not_an_overwrite(self, client, scoped):
        cid, did, storage, _ = await _cartao(scoped, nome_mae="Maria Antiga", nome_mae_origem="manual")
        await _ler(scoped, cid, did, storage, _leitura())
        assert _cliente(scoped, cid)["nome_mae"] == "Maria Antiga"
