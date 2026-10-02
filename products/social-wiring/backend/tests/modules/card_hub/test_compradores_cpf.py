"""`cpf` on `POST .../compradores` (atendimento-partes-imoveis, Wave C0 item 2).

A typed CPF on a NEW pessoa física is stored with `cpf_origem='manual'` (the
manual-edit quinteto); it is NEVER written over the CPF of an existing person
— a different one opens an admin conflict — and never mints a duplicate.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_compradores import _atendimento, _auth, _seed

CPF = "52998224725"
CPF_FMT = "529.982.247-25"
OUTRO_CPF = "11144477735"


def _card(scoped, *extras):
    cid, aid = str(uuid4()), str(uuid4())
    _seed(
        scoped,
        clientes=[cliente_row(cid, nome="Luciano"), *extras],
        atendimentos=[_atendimento(aid, cid)],
    )
    return cid


def _clientes(scoped) -> list[dict]:
    return scoped.table("clientes").select("*").execute().data


class TestNewPessoaFisicaWithCpf:
    def test_cpf_is_stored_canonical_with_manual_provenance(self, client, scoped):
        cid = _card(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Mauricio", "cpf": CPF_FMT},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        nova = next(c for c in _clientes(scoped) if c["id"] == r.json()["cliente"]["id"])
        assert nova["cpf"] == "529.982.247-25"  # canonical, punctuated
        assert nova["cpf_origem"] == "manual"
        assert nova["cpf_documento_id"] is None and nova["cpf_em"]

    def test_cpf_is_optional(self, client, scoped):
        cid = _card(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores", json={"nome": "Sem CPF"}, headers=_auth()
        )
        assert r.status_code == 201
        nova = next(c for c in _clientes(scoped) if c["id"] == r.json()["cliente"]["id"])
        assert not nova.get("cpf") and not nova.get("cpf_origem")

    @pytest.mark.parametrize("invalido", ["123", "11111111111", "529.982.247-26", "abc"])
    def test_an_invalid_cpf_is_422_and_creates_nothing(self, client, scoped, invalido):
        cid = _card(scoped)
        antes = len(_clientes(scoped))
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria", "cpf": invalido},
            headers=_auth(),
        )
        assert r.status_code == 422, r.text
        assert len(_clientes(scoped)) == antes

    def test_a_cpf_already_held_by_another_person_is_409_not_a_duplicate(self, client, scoped):
        existente = cliente_row(str(uuid4()), nome="Maria Existente", cpf=CPF_FMT)
        cid = _card(scoped, existente)
        antes = len(_clientes(scoped))
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Nova", "cpf": CPF},
            headers=_auth(),
        )
        assert r.status_code == 409, r.text
        assert "Maria Existente" in r.text
        assert len(_clientes(scoped)) == antes

    def test_cpf_with_a_company_is_refused(self, client, scoped):
        cid = _card(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"cnpj": "11222333000181", "cpf": CPF},
            headers=_auth(),
        )
        assert r.status_code == 400, r.text


class TestLinkingAnExistingPessoaWithCpf:
    def _vincular(self, client, cid, existente_id, cpf):
        return client.post(
            f"/api/clientes/{cid}/compradores",
            json={"cliente_id": existente_id, "cpf": cpf},
            headers=_auth(),
        )

    def test_a_differing_cpf_never_overwrites_it_opens_a_conflict(self, client, scoped):
        existente = cliente_row(
            str(uuid4()), nome="Maria", cpf=CPF, cpf_origem="manual"
        )
        cid = _card(scoped, existente)
        scoped.set_table_data("cliente_campo_conflitos", [])

        r = self._vincular(client, cid, existente["id"], OUTRO_CPF)

        assert r.status_code == 201, r.text
        assert next(c for c in _clientes(scoped) if c["id"] == existente["id"])["cpf"] == CPF
        (conflito,) = scoped.table("cliente_campo_conflitos").select("*").execute().data
        assert (conflito["campo"], conflito["valor_anterior"], conflito["valor_proposto"]) == (
            "cpf", CPF, "111.444.777-35",  # the PROPOSED value arrives canonical
        )
        assert conflito["status"] == "pendente" and conflito["origem_proposto"] == "manual"

    def test_the_same_cpf_or_none_on_file_writes_nothing(self, client, scoped):
        com_cpf = cliente_row(str(uuid4()), nome="Com CPF", cpf=CPF_FMT)
        sem_cpf = cliente_row(str(uuid4()), nome="Sem CPF")
        cid = _card(scoped, com_cpf, sem_cpf)
        scoped.set_table_data("cliente_campo_conflitos", [])

        assert self._vincular(client, cid, com_cpf["id"], CPF).status_code == 201
        assert self._vincular(client, cid, sem_cpf["id"], CPF).status_code == 201

        assert scoped.table("cliente_campo_conflitos").select("*").execute().data == []
        por_id = {c["id"]: c for c in _clientes(scoped)}
        assert por_id[com_cpf["id"]]["cpf"] == CPF_FMT
        assert not por_id[sem_cpf["id"]].get("cpf")
