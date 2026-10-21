"""AGREEMENT GATE, consumer side (owner decision 2026-10-13).

The seed emits a critical identity field only when two independent
transcriptions agree; otherwise the field is EMPTY and both readings ride in
`IdentityFields.divergencias` + the aviso `divergencia_leituras`. This module
pins that social-wiring (a) writes NOTHING to `clientes` for such a field and
(b) opens a pending `cliente_campo_conflitos` review carrying BOTH readings —
no heuristic picks a winner.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import identidade_extracao_service as svc
from app.services import clientes_service
from noctusai_lib.integrations.documents import (
    ExtractionConfidence,
    FakeIdentityExtractor,
    IdentityFields,
    TextSource,
)
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_identidade_extracao import (
    ORG_UUID,
    _cliente,
    _documento,
    _setup,
)


def _divergente() -> IdentityFields:
    return IdentityFields(
        cpf="412.954.238-98",
        cpf_confianca=ExtractionConfidence.ALTA,
        source=TextSource.OCR,
        aviso="releitura_modelo_superior+divergencia_leituras",
        aviso_mensagem="releitura: SEM valor — nome: ANA SILVA ≠ ANA SOUZA",
        leituras_alternativas=(("nome", "ANA SILVA"), ("nome", "ANA SOUZA")),
        divergencias=(("nome", ("ANA SILVA", "ANA SOUZA")),),
    )


def _conflitos(scoped) -> list[dict]:
    return scoped.table("cliente_campo_conflitos").select("*").execute().data


@pytest.mark.asyncio
async def test_a_diverged_field_opens_a_review_with_both_readings_and_writes_nothing(client, scoped):
    cid, did, storage = await _setup(scoped, tipo="rg", cliente={"nome_oficial": None})
    scoped.set_table_data("cliente_campo_conflitos", [])

    out = await svc.extrair_identidade(
        scoped, storage, ORG_UUID, UUID(cid), UUID(did),
        extractor=FakeIdentityExtractor(_divergente()),
    )

    assert out["aplicado_ao_cliente"].get("nome_oficial") in (None, False)
    assert not _cliente(scoped, cid).get("nome_oficial")
    abertos = [c for c in _conflitos(scoped) if c["status"] == "pendente"]
    assert len(abertos) == 1
    c = abertos[0]
    assert c["campo"] == "nome_oficial"
    assert {c["valor_anterior"], c["valor_proposto"]} == {"ANA SILVA", "ANA SOUZA"}
    assert c["fonte_id"] == did
    # the divergence aviso survives on the document row for the human
    assert "divergencia_leituras" in (_documento(scoped, did)["extracao_aviso"] or "").split("+")
    # the agreeing CPF was applied as usual
    assert _cliente(scoped, cid)["cpf"]


@pytest.mark.asyncio
async def test_a_single_uncorroborated_reading_opens_a_review_without_a_prior_value(client, scoped):
    cid, did, storage = await _setup(scoped, tipo="rg")
    scoped.set_table_data("cliente_campo_conflitos", [])
    f = IdentityFields(
        source=TextSource.OCR,
        aviso="divergencia_leituras",
        divergencias=(("data_nascimento", ("1980-05-12",)),),
    )
    await svc.extrair_identidade(
        scoped, storage, ORG_UUID, UUID(cid), UUID(did), extractor=FakeIdentityExtractor(f),
    )
    (c,) = _conflitos(scoped)
    assert c["campo"] == "data_nascimento"
    assert c["valor_anterior"] is None and c["valor_proposto"] == "1980-05-12"


async def _le(scoped, storage, cid, did):
    return await svc.extrair_identidade(
        scoped, storage, ORG_UUID, UUID(cid), UUID(did),
        extractor=FakeIdentityExtractor(_divergente()),
    )


def _de_nome(scoped) -> list[dict]:
    return [c for c in _conflitos(scoped) if c["campo"] == "nome_oficial"]


@pytest.mark.asyncio
async def test_a_reading_differing_from_the_value_on_file_opens_a_review(client, scoped):
    cid, did, storage = await _setup(scoped, tipo="rg", cliente={"nome_oficial": "ANA SILVA SOUZA"})
    scoped.set_table_data("cliente_campo_conflitos", [])
    await _le(scoped, storage, cid, did)
    (c,) = _de_nome(scoped)
    assert c["status"] == "pendente"
    assert c["valor_anterior"] == "ANA SILVA SOUZA"
    assert c["valor_proposto"] == "ANA SOUZA"
    assert c["origem_proposto"] == svc.ORIGEM_LEITURA_B
    assert not c.get("protege_correcao")
    # never overwritten without approval
    assert _cliente(scoped, cid)["nome_oficial"] == "ANA SILVA SOUZA"


@pytest.mark.asyncio
async def test_a_reading_agreeing_with_the_value_on_file_opens_nothing(client, scoped):
    cid, did, storage = await _setup(scoped, tipo="rg", cliente={"nome_oficial": "Ana Silva"})
    scoped.set_table_data("cliente_campo_conflitos", [])
    await _le(scoped, storage, cid, did)
    assert _de_nome(scoped) == []


@pytest.mark.asyncio
async def test_an_owner_correction_on_file_makes_the_review_protective(client, scoped):
    cid, did, storage = await _setup(scoped, tipo="rg", cliente={"nome_oficial": "ANA PEREIRA"})
    scoped.set_table_data("cliente_campo_conflitos", [])
    clientes_service.update_cliente(
        scoped, ORG_UUID, UUID(cid), acting_user_id=uuid4(), is_admin=True,
        nome_oficial="ANA CORRIGIDA",
    )
    await _le(scoped, storage, cid, did)
    (c,) = _de_nome(scoped)
    assert c["valor_anterior"] == "ANA CORRIGIDA"
    assert c["protege_correcao"] is True
    assert _cliente(scoped, cid)["nome_oficial"] == "ANA CORRIGIDA"


@pytest.mark.asyncio
async def test_approve_applies_the_reading_and_reject_is_never_reraised(client, scoped):
    cid, did, storage = await _setup(scoped, tipo="rg", cliente={"nome_oficial": "ANA PEREIRA"})
    scoped.set_table_data("cliente_campo_conflitos", [])
    await _le(scoped, storage, cid, did)
    (c,) = _de_nome(scoped)
    svc.resolver_conflito(scoped, ORG_UUID, UUID(c["id"]), aceitar=False, decidido_por=uuid4())
    assert _cliente(scoped, cid)["nome_oficial"] == "ANA PEREIRA"
    await _le(scoped, storage, cid, did)
    assert [x for x in _de_nome(scoped) if x["status"] == "pendente"] == []


@pytest.mark.asyncio
async def test_approving_the_review_applies_the_reading(client, scoped):
    cid, did, storage = await _setup(scoped, tipo="rg", cliente={"nome_oficial": "ANA PEREIRA"})
    scoped.set_table_data("cliente_campo_conflitos", [])
    await _le(scoped, storage, cid, did)
    (c,) = _de_nome(scoped)
    svc.resolver_conflito(scoped, ORG_UUID, UUID(c["id"]), aceitar=True, decidido_por=uuid4())
    assert _cliente(scoped, cid)["nome_oficial"] == "ANA SOUZA"


@pytest.mark.asyncio
async def test_document_level_divergences_open_no_cliente_review(client, scoped):
    cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
    scoped.set_table_data("cliente_campo_conflitos", [])
    f = IdentityFields(
        source=TextSource.OCR,
        aviso="divergencia_leituras",
        divergencias=(("conjuges", ("ANA / JOAO", "ANA / JOAQUIM")),),
    )
    await svc.extrair_identidade(
        scoped, storage, ORG_UUID, UUID(cid), UUID(did), extractor=FakeIdentityExtractor(f),
    )
    assert _conflitos(scoped) == []
