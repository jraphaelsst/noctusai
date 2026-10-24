"""F98 — a Serasa Crednet read on an ANTIGO proprietário.

An antigo is a `clientes` row (parte `lado='vendedor'`, `papel=
'antigo_proprietario'`), so the SAME machinery a vendedor goes through must
hold end to end: the `serasa_crednet` checklist slot is offered on him, a
read creates his `cliente_empresa_participacoes`, and the company surfaces in
the Certidões partes' ANTIGOS group (`ANT EMP n`, never the vendedores'), so
its certidões can be emitted with the existing buttons.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from noctusai_lib.integrations.cnpj_registry import FakeCnpjRegistryLookup
from noctusai_lib.testing.mocks import MockSupabaseClient

from app.dependencies import coerce_org_uuid
from app.modules.card_hub import certidoes_partes_service as partes_svc
from app.modules.card_hub import crednet_service, documento_checklist_service as checklist_svc
from tests.support.document_fakes import (
    ALTA,
    CNPJ_VALIDO,
    CPF_VALIDO,
    CrednetFields,
    FakeCrednetExtractor,
    OcorrenciaCrednet,
    ParticipacaoCrednet,
)

ORG_ID = coerce_org_uuid("test-org-antigo-crednet")
NADA = OcorrenciaCrednet(constam=False, quantidade=0)


@pytest.fixture
def client():
    scoped = MockSupabaseClient().schema("social_wiring")
    for table in (
        "clientes", "cliente_documentos", "empresas", "cliente_empresa_participacoes",
        "cliente_campo_conflitos", "empresa_campo_conflitos", "certidao_consultas",
        "certidao_resultados", "atendimentos", "atendimento_partes", "imovel_proprietarios",
        "atendimento_negociacao_parcelas",
    ):
        scoped.set_table_data(table, [])
    return scoped


def _cliente(cid: str, nome: str) -> dict:
    return {
        "id": cid, "org_id": str(ORG_ID), "nome": nome, "nome_oficial": None, "nome_oficial_origem": None,
        "cpf": None, "cpf_origem": None, "data_nascimento": None, "data_nascimento_origem": None,
        "nome_mae": None, "nome_mae_origem": None, "nome_mae_confirmado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def _seed(client):
    titular, antigo, at_id, doc_id = (str(uuid4()) for _ in range(4))
    client.table("clientes").insert([_cliente(titular, "Comprador"), _cliente(antigo, "Zé Antigo")]).execute()
    client.table("atendimentos").insert({
        "id": at_id, "org_id": str(ORG_ID), "cliente_id": titular,
        "substituida_por": None, "arquivado": False,
    }).execute()
    client.table("atendimento_partes").insert({
        "id": str(uuid4()), "org_id": str(ORG_ID), "atendimento_id": at_id, "cliente_id": antigo,
        "lado": "vendedor", "papel": "antigo_proprietario",
    }).execute()
    client.table("cliente_documentos").insert({
        "id": doc_id, "org_id": str(ORG_ID), "cliente_id": antigo,
        "storage_path": f"{ORG_ID}/clientes/{antigo}/{doc_id}", "nome_original": "crednet.pdf",
        "mime_type": "application/pdf", "tamanho_bytes": 1024, "tipo_documento": "serasa_crednet",
        "deleted_at": None, "created_at": "2026-01-01T00:00:00+00:00",
    }).execute()
    return titular, antigo, at_id, doc_id


def test_serasa_crednet_slot_is_offered_on_an_antigo(client):
    _titular, antigo, _at, _doc = _seed(client)
    chaves = [i["key"] for i in checklist_svc.listar(client, ORG_ID, antigo)["items"]]
    assert "serasa_crednet" in chaves


@pytest.mark.asyncio
async def test_crednet_on_an_antigo_creates_participacao_and_company_lands_in_the_antigos_group(client):
    titular, antigo, at_id, doc_id = _seed(client)
    fields = CrednetFields(
        consulta_em=datetime.now().replace(microsecond=0) - timedelta(days=5),
        protocolo="1234567", cpf=CPF_VALIDO, cpf_valido=True, nome="ZE ANTIGO",
        nome_mae="MAE DO ZE", data_nascimento=date(1960, 1, 1),
        pendencias_internas=NADA, pendencias_financeiras=NADA, protesto_estadual=NADA,
        cheques_sem_fundo=NADA,
        participacoes=(ParticipacaoCrednet(
            cnpj=CNPJ_VALIDO, cnpj_valido=True, razao_social="ANTIGA LTDA", participacao_pct=100, confianca=ALTA,
        ),),
        confiancas={"nome": ALTA, "cpf": ALTA, "data_nascimento": ALTA, "nome_mae": ALTA}, rotulos={},
    )
    doc = client.table("cliente_documentos").select("*").eq("id", doc_id).execute().data[0]
    await crednet_service.aplicar_leitura(
        client, ORG_ID, antigo, doc_id, doc, b"%PDF-1.4 fake",
        extractor=FakeCrednetExtractor(result=fields),
        cnpj_registry_lookup=FakeCnpjRegistryLookup(), notification_service=None,
    )

    # The antigo's own CPF fills the party (the existing apply path).
    assert client.table("clientes").select("*").eq("id", antigo).execute().data[0]["cpf"] == "412.954.238-98"
    part = client.table("cliente_empresa_participacoes").select("*").eq("cliente_id", antigo).execute().data
    assert len(part) == 1 and part[0]["origem"] == "serasa_crednet"

    todas = partes_svc._empresas_derivadas(client, ORG_ID, titular, [], atendimento_id=at_id)
    assert [(e["rotulo"], e["grupo"]) for e in todas] == [("ANT EMP 1", "antigo_proprietario")]
    assert todas[0]["nome"] == "ANTIGA LTDA"
