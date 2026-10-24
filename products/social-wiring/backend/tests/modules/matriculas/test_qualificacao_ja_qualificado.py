"""F97 — a seller the título act names only as "já qualificado" carries the
CPF/RG/estado civil the earlier act qualified him with, and the título's
ADQUIRENTE qualification lands as machine-pending suggestions on the card's
seller (by CPF, else by normalised name), dated by the act.

Synthetic data only: every name is invented, every CPF is check-digit-valid
and fictitious.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from app.modules.matriculas import ato_detalhes_service as detalhes_svc
from app.modules.matriculas import estrutura_service as svc
from app.modules.matriculas import qualificacao_service as qsvc
from app.modules.matriculas import titulo_service
from tests.modules.matriculas.conftest import (
    CODIGO,
    ORG_ID,
    extracao_row,
    negociacao_row,
    registry_row,
    seed,
)

ORG = UUID(ORG_ID)
HOJE = date(2026, 10, 24)

CPF_JOAO = "529.982.247-25"
CPF_MARCOS = "123.456.789-09"
CPF_OUTRO = "111.444.777-35"

TEXTO = (
    "MATRÍCULA Nº 12.345\nFICHA 01\nIMÓVEL: Apartamento ficticio nº 12 da Rua dos Exemplos.\n"
    "R-3/12.345 - Em 10 de março de 2009. Por escritura de 02/03/2009, a proprietária "
    "CONSTRUTORA EXEMPLO LTDA vendeu o imóvel desta matrícula a JOÃO CARLOS PEREIRA, "
    "brasileiro, divorciado, piloto, RG nº 11.111.111-1-SSP/SP, CPF nº "
    f"{CPF_JOAO}, residente e domiciliado na Rua A, 1, nesta Capital, pelo valor de "
    "R$ 100.000,00.\n"
    "R-7/12.345 - Em 15 de abril de 2024. Por escritura de 01/04/2024, o proprietário "
    "JOÃO CARLOS PEREIRA, já qualificado, transmitiu por venda e compra o imóvel desta "
    "matrícula a MARCOS ANTÔNIO SOUZA, brasileiro, casado, psicólogo, RG nº "
    f"12.345.678-9-SSP/SP, CPF nº {CPF_MARCOS}, residente e domiciliado na Rua B, 2, "
    "nesta Capital, pelo valor de R$ 500.000,00.\n"
)


def _cliente(nome: str, **extra) -> dict:
    return {"id": str(uuid4()), "org_id": ORG_ID, "nome_completo": nome, "nome": nome, **extra}


def _card_com_vendedor(scoped, vendedor: dict, *, documentos=()) -> str:
    """One deal on this imóvel with `vendedor` as its seller party."""
    atendimento_id = str(uuid4())
    scoped.set_table_data("atendimento_negociacao", [negociacao_row(atendimento_id)])
    scoped.set_table_data("atendimento_partes", [{
        "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atendimento_id,
        "cliente_id": vendedor["id"], "lado": "vendedor", "papel": "proprietario",
    }])
    scoped.set_table_data("cliente_documentos", list(documentos))
    return atendimento_id


def _seed(scoped, *, clientes=()):
    ext = extracao_row(texto=TEXTO)
    seed(scoped, registry=[registry_row()], extracoes=[ext], clientes=list(clientes))
    return ext


def _segmentar(scoped, ext):
    atos = svc.atos_da_extracao(scoped, ORG, ext)
    detalhes = detalhes_svc.detalhes_por_ato(scoped, ORG, ext, atos)
    return atos, detalhes


def _r7(atos, detalhes):
    ato = next(a for a in atos if a["kind"] == "R" and a["numero"] == 7)
    return ato, detalhes[str(ato["id"])]


def _cliente_atual(scoped, cliente_id):
    return scoped.table("clientes").select("*").eq("id", cliente_id).execute().data[0]


# ─── 1. the act's party details + antigos ───────────────────────────────


def test_the_ja_qualificado_seller_carries_his_earlier_cpf(scoped):
    _seed(scoped)

    out = titulo_service.antigos_proprietarios(scoped, ORG, CODIGO, hoje=HOJE)

    assert out["transmitentes"] == [
        {"nome": "JOÃO CARLOS PEREIRA", "cpf_cnpj": CPF_JOAO, "qualificado_em": "R-3"}
    ]
    assert out["exige_certidoes"] is True


def test_the_act_row_stores_the_resolved_qualification(scoped):
    ext = _seed(scoped)
    _ato, det = _r7(*_segmentar(scoped, ext))
    (joao,) = det["transmitentes"]
    assert joao["cpf_cnpj"] == CPF_JOAO
    assert (joao["rg"], joao["estado_civil"], joao["profissao"]) == (
        "11.111.111-1", "divorciado", "piloto",
    )


def test_a_stale_machine_row_re_derives_on_read_without_re_transcribing(scoped):
    ext = _seed(scoped)
    _ato, det = _r7(*_segmentar(scoped, ext))
    scoped.table(detalhes_svc.DETALHES_TABLE).update(
        {"transmitentes": [{"nome": "JOÃO CARLOS PEREIRA", "cpf_cnpj": None}]}
    ).eq("id", det["id"]).execute()

    _ato, healed = _r7(*_segmentar(scoped, ext))

    assert healed["transmitentes"][0]["cpf_cnpj"] == CPF_JOAO


def test_a_human_confirmed_row_is_never_rewritten_but_resolves_at_read(scoped):
    ext = _seed(scoped)
    _ato, det = _r7(*_segmentar(scoped, ext))
    scoped.table(detalhes_svc.DETALHES_TABLE).update({
        "transmitentes": [{"nome": "JOÃO CARLOS PEREIRA", "cpf_cnpj": None}],
        "origem": "confirmado", "confirmado_por": "u-1",
    }).eq("id", det["id"]).execute()

    out = titulo_service.antigos_proprietarios(scoped, ORG, CODIGO, hoje=HOJE)

    assert out["transmitentes"][0]["cpf_cnpj"] == CPF_JOAO
    _ato, linha = _r7(*_segmentar(scoped, ext))
    assert linha["transmitentes"][0]["cpf_cnpj"] is None  # the human row stays


# ─── 3. the título adquirente's qualification -> the card's seller ───────


def test_adquirente_suggestions_land_on_the_seller_matched_by_name(scoped):
    marcos = _cliente("Marcos Antonio Souza")
    _seed(scoped, clientes=[marcos])
    _card_com_vendedor(scoped, marcos)

    _rodar(scoped)

    atual = _cliente_atual(scoped, marcos["id"])
    assert atual["cpf"] == CPF_MARCOS
    assert atual["rg"] == "12.345.678-9"
    assert atual["estado_civil"] == "casado"
    assert atual["profissao"] == "psicólogo"
    assert atual["nacionalidade"] == "brasileiro"
    assert atual["estado_civil_origem"] == "matricula"
    assert atual["estado_civil_confirmado_por"] is None  # a suggestion, never a confirmation
    (q,) = [
        r for r in scoped.table("matricula_qualificacoes").select("*").execute().data
        if r["cpf_cnpj"] == CPF_MARCOS
    ]
    assert q["vinculo_status"] == "vinculado" and q["cliente_id"] == marcos["id"]


def test_an_older_party_of_the_chain_is_never_bound_to_a_seller_by_name(scoped):
    homonimo = _cliente("João Carlos Pereira")
    _seed(scoped, clientes=[homonimo])
    _card_com_vendedor(scoped, homonimo)
    ext = scoped.table("matricula_extracoes").select("*").execute().data[0]

    qsvc.qualificacoes_da_extracao(
        scoped, ORG, ext, svc.atos_da_extracao(scoped, ORG, ext)
    )

    assert _cliente_atual(scoped, homonimo["id"]).get("cpf") is None


def _com_certidao_nascimento(estado_civil_extra: dict) -> tuple[dict, dict]:
    doc_id = str(uuid4())
    marcos = _cliente(
        "Marcos Antonio Souza", cpf=CPF_MARCOS, estado_civil="solteiro",
        estado_civil_origem="certidao_nascimento", estado_civil_documento_id=doc_id,
        **estado_civil_extra,
    )
    documento = {
        "id": doc_id, "org_id": ORG_ID, "cliente_id": marcos["id"],
        "tipo_documento": "certidao_nascimento", "extracao_data_emissao": "2009-05-01",
        "extracao_estado_civil": "solteiro",
    }
    return marcos, documento


def _rodar(scoped):
    ext = scoped.table("matricula_extracoes").select("*").execute().data[0]
    qsvc.qualificacoes_da_extracao(
        scoped, ORG, ext, svc.atos_da_extracao(scoped, ORG, ext)
    )


def test_a_newer_registry_estado_civil_beats_an_older_certidao_as_a_suggestion(scoped):
    marcos, documento = _com_certidao_nascimento({})
    _seed(scoped, clientes=[marcos])
    _card_com_vendedor(scoped, marcos, documentos=[documento])

    _rodar(scoped)

    atual = _cliente_atual(scoped, marcos["id"])
    assert atual["estado_civil"] == "casado"
    assert atual["estado_civil_origem"] == "matricula"
    assert atual["estado_civil_confirmado_por"] is None
    (audit,) = [
        c for c in scoped.table("cliente_campo_conflitos").select("*").execute().data
        if c["campo"] == "estado_civil"
    ]
    assert audit["status"] == "resolvido_automatico"
    assert "evidencia_mais_recente" in (audit.get("motivo_resolucao") or "")


def test_a_confirmed_estado_civil_is_never_overwritten_by_a_newer_act(scoped):
    marcos, documento = _com_certidao_nascimento(
        {"estado_civil_confirmado_por": "u-1", "estado_civil_confirmado_em": "2026-01-01"}
    )
    _seed(scoped, clientes=[marcos])
    _card_com_vendedor(scoped, marcos, documentos=[documento])

    _rodar(scoped)

    assert _cliente_atual(scoped, marcos["id"])["estado_civil"] == "solteiro"


def test_a_name_matched_seller_with_a_different_cpf_gets_a_conflict_not_an_overwrite(scoped):
    marcos = _cliente("Marcos Antônio Souza", cpf=CPF_OUTRO, cpf_origem="manual")
    _seed(scoped, clientes=[marcos])
    _card_com_vendedor(scoped, marcos)

    _rodar(scoped)

    assert _cliente_atual(scoped, marcos["id"])["cpf"] == CPF_OUTRO
    conflitos = [
        c for c in scoped.table("cliente_campo_conflitos").select("*").execute().data
        if c["campo"] == "cpf"
    ]
    assert [c["status"] for c in conflitos] == ["pendente"]
    assert conflitos[0]["valor_proposto"] == CPF_MARCOS
