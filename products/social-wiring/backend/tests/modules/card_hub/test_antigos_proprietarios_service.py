"""`antigos_proprietarios_service` — the Certidões tab's previous-owner group
(owner decisions 2026-10-05). The matrícula reading is handed in through the
service's DI seam (`ler_antigos`); everything else runs against the mock DB.
Every name / CPF / CNPJ is synthetic."""
from __future__ import annotations

from uuid import uuid4

import pytest
from noctusai_lib.primitives.exceptions import ConflictError, ValidationError_

from app.modules.card_hub import antigos_proprietarios_service as svc
from app.modules.card_hub import certidoes_partes_service as certidoes_svc
from app.modules.card_hub import partes_service
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_certidoes_matriz import _atendimento, _seed_tables

CPF_A = "52998224725"
CPF_B = "11144477735"
CNPJ_A = "11444777000161"
USER = uuid4()


def _creds_ok(_org_id):
    return []


def _creds_faltando(_org_id):
    return ["Chave InfoSimples ausente."]


def _info(*transmitentes, exige=True, origem="titulo_confirmado"):
    return lambda *_a, **_k: {
        "transmitentes": [{"nome": n, "cpf_cnpj": d} for n, d in transmitentes],
        "exige_certidoes": exige,
        "origem": origem,
        "sem_registro": False,
        "ultima_transferencia": {"data_registro": "2024-03-01", "natureza": "compra_e_venda"},
    }


def _card(scoped):
    cid, aid = str(uuid4()), str(uuid4())
    _seed_tables(scoped)
    for t in ("atendimento_negociacao", "atendimento_negociacao_termos", "organizacao_negociacao_defaults"):
        scoped.set_table_data(t, [])
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Titular", cpf="39053344705")])
    scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
    scoped.set_table_data("atendimento_negociacao", [
        {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid, "imovel_codigo": "AP0001"},
    ])
    return cid, aid


def _sync(scoped, cid, info, creds=_creds_ok):
    return svc.sincronizar(
        scoped, ORG_ID, cid, user_id=USER, check_credentials=creds, ler_antigos=info,
    )


class TestSincronizar:
    def test_recent_transfer_creates_the_group_and_starts_emission(self, scoped):
        cid, aid = _card(scoped)
        out = _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A), ("Construtora Exemplo", CNPJ_A)))
        assert [c["tipo_pessoa"] for c in out["criados"]] == ["PF", "PJ"]
        assert [e["status"] for e in out["emissoes"]] == ["solicitada", "solicitada"]
        assert all(e["consulta_id"] for e in out["emissoes"])
        antigos = partes_service.listar_antigos(scoped, ORG_ID, cid)
        assert [a["rotulo"] for a in antigos] == ["ANT 1", "ANT 2"]
        assert {a["papel"] for a in antigos} == {"antigo_proprietario"}
        assert {a["origem"] for a in antigos} == {"matricula"}
        consultas = scoped.table("certidao_consultas").select("*").execute().data
        assert len(consultas) == 2

    def test_previous_owners_are_never_in_the_parties_list(self, scoped):
        cid, _aid = _card(scoped)
        _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A)))
        _alvo, itens = partes_service.listar_partes(scoped, ORG_ID, cid)
        assert [i["rotulo"] for i in itens] == ["COMP 1"]

    def test_certidoes_payload_carries_the_group_after_the_sellers(self, scoped):
        cid, _aid = _card(scoped)
        _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A)))
        partes = certidoes_svc.montar(scoped, ORG_ID, cid)["partes"]
        assert [(p["grupo"], p["rotulo"]) for p in partes] == [
            ("comprador", "COMP 1"), ("antigo_proprietario", "ANT 1"),
        ]
        assert partes[1]["papel"] == "antigo_proprietario"

    def test_is_idempotent(self, scoped):
        cid, _aid = _card(scoped)
        info = _info(("Antigo Dono Exemplo", CPF_A))
        assert len(_sync(scoped, cid, info)["criados"]) == 1
        again = _sync(scoped, cid, info)
        assert again["criados"] == [] and again["emissoes"] == []
        assert len(again["ja_no_card"]) == 1

    def test_dispensed_deal_creates_nothing(self, scoped):
        cid, _aid = _card(scoped)
        svc.dispensar(scoped, ORG_ID, cid, motivo="Acordo com o cliente", usuario_id=USER,
                      ler_antigos=_info())
        out = _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A)))
        assert out["ignorado"] == "dispensado" and out["criados"] == []

    def test_transfer_of_five_years_or_more_creates_nothing(self, scoped):
        cid, _aid = _card(scoped)
        out = _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A), exige=False))
        assert out["ignorado"] == "transferencia_5_anos_ou_mais"
        assert partes_service.listar_antigos(scoped, ORG_ID, cid) == []

    def test_a_manual_override_names_nobody_so_nothing_is_created(self, scoped):
        cid, _aid = _card(scoped)
        out = _sync(scoped, cid, _info(origem="manual"))
        assert out["ignorado"] == "matricula_nao_nomeia_antigos"

    def test_missing_credentials_are_reported_not_swallowed(self, scoped):
        cid, _aid = _card(scoped)
        out = _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A)), creds=_creds_faltando)
        assert len(out["criados"]) == 1
        assert out["emissoes"][0]["status"] == "nao_iniciada"
        assert out["emissoes"][0]["codigo"] == "CREDENCIAIS_AUSENTES"

    def test_a_transmitente_without_a_document_is_added_but_emission_is_named_missing(self, scoped):
        cid, _aid = _card(scoped)
        out = _sync(scoped, cid, _info(("Antigo Sem Documento", None)))
        assert out["emissoes"][0]["codigo"] == "DOCUMENTO_AUSENTE"


class TestDispensa:
    def test_requires_a_motivo(self, scoped):
        cid, _aid = _card(scoped)
        with pytest.raises(ValidationError_):
            svc.dispensar(scoped, ORG_ID, cid, motivo=" a ", usuario_id=USER)

    def test_stamps_who_when_why_and_can_be_undone(self, scoped):
        cid, aid = _card(scoped)
        out = svc.dispensar(scoped, ORG_ID, cid, motivo="Acordo com o cliente", usuario_id=USER,
                            ler_antigos=_info())
        assert out["dispensado"]["motivo"] == "Acordo com o cliente"
        assert svc.esta_dispensado(scoped, ORG_ID, aid)
        out = svc.reativar(scoped, ORG_ID, cid, usuario_id=USER, ler_antigos=_info())
        assert out["dispensado"] is None and not svc.esta_dispensado(scoped, ORG_ID, aid)


class TestManual:
    def test_add_and_remove_by_hand(self, scoped):
        cid, _aid = _card(scoped)
        out = svc.adicionar_manual(
            scoped, ORG_ID, cid, nome="Antigo Manual Exemplo", cpf=CPF_B,
            user_id=USER, check_credentials=_creds_ok,
        )
        assert out["parte"]["origem"] == "manual" and out["emissao"]["status"] == "solicitada"
        with pytest.raises(ConflictError):
            svc.adicionar_manual(
                scoped, ORG_ID, cid, nome="Antigo Manual Exemplo", cpf=CPF_B,
                user_id=USER, check_credentials=_creds_ok,
            )
        svc.remover(scoped, ORG_ID, cid, out["parte"]["parte_id"])
        assert partes_service.listar_antigos(scoped, ORG_ID, cid) == []

    def test_remove_refuses_a_party_that_is_not_a_previous_owner(self, scoped):
        cid, aid = _card(scoped)
        seller = str(uuid4())
        scoped.set_table_data("clientes", [
            *scoped.table("clientes").select("*").execute().data, cliente_row(seller, nome="Vend", cpf=CPF_B),
        ])
        from tests.modules.card_hub.test_certidoes_matriz import _parte
        parte = _parte(aid, seller)
        scoped.set_table_data("atendimento_partes", [parte])
        with pytest.raises(ValidationError_):
            svc.remover(scoped, ORG_ID, cid, parte["id"])

    def test_invalid_document_is_refused(self, scoped):
        cid, _aid = _card(scoped)
        with pytest.raises(ValidationError_):
            svc.adicionar_manual(scoped, ORG_ID, cid, nome="X Y", cpf="11111111111",
                                 user_id=USER, check_credentials=_creds_ok)


class TestEstado:
    def test_header_state_is_required_with_masked_transmitentes(self, scoped):
        cid, _aid = _card(scoped)
        out = svc.estado(scoped, ORG_ID, cid, ler_antigos=_info(("Antigo Dono Exemplo", CPF_A)))
        assert out["exigido"] is True and out["motivo"] == "transferencia_menos_de_5_anos"
        assert out["transmitentes"][0]["documento_mascarado"] == "***.982.247-**"
        assert out["sincronizacao_pendente"] == 1 and out["dispensado"] is None
