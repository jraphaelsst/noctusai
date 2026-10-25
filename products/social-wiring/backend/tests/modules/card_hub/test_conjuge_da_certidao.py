"""The spouse a certidão de casamento READ (no CPF on the page) is offered as a
one-click party, never hand-typed (`conjuge_da_certidao_service`).

Invented names; synthetic data.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import conjuge_da_certidao_service as svc
from noctusai_lib.primitives.exceptions import ConflictError

from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_certidao_casamento_conjuge_completo import (
    _cartao, _clientes, _leitura, _ler, _outro,
)
from tests.modules.card_hub.test_identidade_extracao import ORG_UUID, _cliente, _documento


async def _lida_sem_cpf(scoped):
    cid, did, storage, aid = await _cartao(scoped)
    await _ler(scoped, cid, did, storage, _leitura(cpf_outro=None))
    return cid, did, aid


class TestSugestao:
    @pytest.mark.asyncio
    async def test_unlinked_spouse_is_suggested_from_the_document(self, client, scoped):
        cid, did, aid = await _lida_sem_cpf(scoped)
        assert len(_clientes(scoped)) == 1  # not created unattended (no CPF)
        out = svc.sugerir(scoped, ORG_UUID, UUID(cid))
        assert out["atendimento_id"] == aid
        [s] = out["items"]
        assert s["nome"] == "RAFAEL MENEZES DO PRADO"
        assert s["data_nascimento"] == "1985-03-10"
        assert (s["documento_id"], s["principal_cliente_id"], s["lado"]) == (did, cid, "comprador")

    @pytest.mark.asyncio
    async def test_not_suggested_once_a_spouse_is_linked(self, client, scoped):
        cid, did, aid = await _lida_sem_cpf(scoped)
        svc.adicionar(scoped, ORG_UUID, UUID(cid), documento_id=UUID(did))
        assert svc.sugerir(scoped, ORG_UUID, UUID(cid))["items"] == []

    @pytest.mark.asyncio
    async def test_a_divorced_reading_suggests_nobody(self, client, scoped):
        cid, did, aid = await _lida_sem_cpf(scoped)
        docs = scoped.table("cliente_documentos").select("*").execute().data
        scoped.set_table_data(
            "cliente_documentos", [{**d, "extracao_estado_civil": "divorciado"} for d in docs]
        )
        assert svc.sugerir(scoped, ORG_UUID, UUID(cid))["items"] == []

    @pytest.mark.asyncio
    async def test_the_vendedor_side_has_no_principal_without_a_proprietario(self, client, scoped):
        cid, did, aid = await _lida_sem_cpf(scoped)
        assert svc.sugerir(scoped, ORG_UUID, UUID(cid), lado="vendedor")["items"] == []


class TestAcao:
    @pytest.mark.asyncio
    async def test_creates_links_and_attributes_with_provenance(self, client, scoped):
        cid, did, aid = await _lida_sem_cpf(scoped)
        parte = svc.adicionar(scoped, ORG_UUID, UUID(cid), documento_id=UUID(did))
        o = _outro(scoped, cid)
        assert parte["cliente_id"] == o["id"] and parte["papel"] == "conjuge"
        assert o["conjuge_cliente_id"] == cid and _cliente(scoped, cid)["conjuge_cliente_id"] == o["id"]
        assert o["conjuge_origem"] == "certidao_casamento" and o["conjuge_documento_id"] == did
        # The attribution ran: person facts machine-pending, never `manual`.
        assert o["data_nascimento"] == "1985-03-10"
        for campo in ("data_nascimento", "nome_mae", "nome_pai", "naturalidade", "estado_civil"):
            assert o[f"{campo}_origem"] == "certidao_casamento", campo
            assert not o.get(f"{campo}_confirmado_em"), campo
        entradas = {e["nome"]: e for e in _documento(scoped, did)["extracao_conjuges"]}
        assert entradas["RAFAEL MENEZES DO PRADO"]["cliente_id"] == o["id"]

    @pytest.mark.asyncio
    async def test_same_name_and_birthdate_is_a_409_with_candidates_then_linked(self, client, scoped):
        cid, did, aid = await _lida_sem_cpf(scoped)
        existente = str(uuid4())
        scoped.set_table_data("clientes", _clientes(scoped) + [cliente_row(
            existente, nome="Rafael Menezes do Prado", data_nascimento="1985-03-10",
        )])
        with pytest.raises(svc.ConjugeCandidatos) as exc:
            svc.adicionar(scoped, ORG_UUID, UUID(cid), documento_id=UUID(did))
        assert [c["cliente_id"] for c in exc.value.details["candidatos"]] == [existente]
        assert len(_clientes(scoped)) == 2  # nothing written by the refusal
        svc.adicionar(
            scoped, ORG_UUID, UUID(cid), documento_id=UUID(did), parte_cliente_id=UUID(existente)
        )
        assert len(_clientes(scoped)) == 2  # linked, not duplicated
        assert _cliente(scoped, cid)["conjuge_cliente_id"] == existente
        assert _cliente(scoped, existente)["nome_mae_origem"] == "certidao_casamento"

    @pytest.mark.asyncio
    async def test_criar_novo_overrides_the_match(self, client, scoped):
        cid, did, aid = await _lida_sem_cpf(scoped)
        scoped.set_table_data("clientes", _clientes(scoped) + [cliente_row(
            str(uuid4()), nome="Rafael Menezes do Prado", data_nascimento="1985-03-10",
        )])
        svc.adicionar(scoped, ORG_UUID, UUID(cid), documento_id=UUID(did), criar_novo=True)
        assert len(_clientes(scoped)) == 3

    @pytest.mark.asyncio
    async def test_a_document_that_suggests_nothing_is_refused(self, client, scoped):
        cid, did, aid = await _lida_sem_cpf(scoped)
        with pytest.raises(ConflictError):
            svc.adicionar(scoped, ORG_UUID, UUID(cid), documento_id=uuid4())


class TestLadoVendedor:
    @pytest.mark.asyncio
    async def test_a_proprietarios_certidao_suggests_and_adds_a_vendedor_side_conjuge(
        self, client, scoped
    ):
        cid, did, aid = await _lida_sem_cpf(scoped)
        scoped.set_table_data("atendimento_partes", [{
            "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid, "cliente_id": cid,
            "lado": "vendedor", "papel": "proprietario", "ordem": 0,
        }])
        [s] = svc.sugerir(scoped, ORG_UUID, UUID(cid), lado="vendedor")["items"]
        assert (s["principal_cliente_id"], s["lado"]) == (cid, "vendedor")
        parte = svc.adicionar(scoped, ORG_UUID, UUID(cid), documento_id=UUID(did), lado="vendedor")
        assert (parte["papel"], parte["lado"]) == ("conjuge", "vendedor")
        assert _outro(scoped, cid)["conjuge_cliente_id"] == cid
