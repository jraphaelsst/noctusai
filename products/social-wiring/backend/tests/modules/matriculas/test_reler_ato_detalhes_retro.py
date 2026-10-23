"""F65/F66 — "Ler novamente" re-derives the machine act details with the
CURRENT parser (never a human-confirmed row), and a seller named only by
back-reference ("retro nomeados e qualificados") resolves from the chain, not
stored as a name. Synthetic data only."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from app.modules.matriculas import ato_detalhes_service as detalhes_svc
from app.modules.matriculas import estrutura_service as svc
from app.modules.matriculas import titulo_service
from tests.modules.matriculas.conftest import (
    CODIGO,
    ORG_ID,
    extracao_row,
    registry_row,
    seed,
)

ORG = UUID(ORG_ID)

TEXTO = (
    "MATRÍCULA Nº 21.748\nFICHA 01\nIMÓVEL: Casa ficticia da Rua dos Exemplos.\n"
    "PROPRIETÁRIOS: JOSE PRIMEIRO FICTICIO, brasileiro, casado; MARIA PRIMEIRA FICTICIA, "
    "brasileira, casada.\n"
    "R-4/21.748 - Em 12/02/1988. Por escritura pública lavrada aos 28/01/1988, os "
    "proprietários retro nomeados e quali-\nficados, transmitiram, a titulo de DOAÇÃO, "
    "o imóvel a ANA QUARTA FICTICIA, brasileira, menor.\n"
)


def _extracao(scoped):
    ext = extracao_row(texto=TEXTO)
    seed(scoped, registry=[registry_row()], extracoes=[ext])
    return ext


def test_back_referenced_sellers_resolve_from_the_abertura_owners(client, scoped):
    _extracao(scoped)

    out = titulo_service.antigos_proprietarios(scoped, ORG, CODIGO, hoje=date(2026, 10, 23))

    nomes = [t["nome"] for t in out["transmitentes"]]
    assert nomes == ["JOSE PRIMEIRO FICTICIO", "MARIA PRIMEIRA FICTICIA"]
    assert not any("retro" in n.lower() or "quali" in n.lower() for n in nomes)


def _linha(scoped, ext):
    atos = svc.atos_da_extracao(scoped, ORG, ext)
    det = detalhes_svc.detalhes_por_ato(scoped, ORG, ext, atos)
    ato = next(a for a in atos if a["kind"] == "R")
    return det[str(ato["id"])]


def test_a_stale_machine_row_is_rederived_by_the_current_parser(client, scoped):
    ext = _extracao(scoped)
    linha = _linha(scoped, ext)
    stale = {
        "transmitentes": [{"nome": "retro nomeados", "cpf_cnpj": None}],
        "data_registro": None,
    }
    scoped.table(detalhes_svc.DETALHES_TABLE).update(stale).eq("id", linha["id"]).execute()

    atos = svc.atos_da_extracao(scoped, ORG, ext)
    det = detalhes_svc.detalhes_por_ato(scoped, ORG, ext, atos)
    nova = det[linha["ato_id"]]

    assert nova["transmitentes"] == []
    assert str(nova["data_registro"])[:10] == "1988-02-12"


def test_rederivar_do_documento_heals_and_spares_human_rows(client, scoped):
    doc_id = "00000000-0000-0000-0000-0000000000d1"
    ext = extracao_row(texto=TEXTO, imovel_documento_id=doc_id)
    seed(scoped, registry=[registry_row()], extracoes=[ext])
    linha = _linha(scoped, ext)
    scoped.table(detalhes_svc.DETALHES_TABLE).update(
        {"data_registro": None, "origem": "sugestao"}
    ).eq("id", linha["id"]).execute()

    assert detalhes_svc.rederivar_do_documento(scoped, ORG, doc_id) == 1
    assert str(_linha(scoped, ext)["data_registro"])[:10] == "1988-02-12"

    scoped.table(detalhes_svc.DETALHES_TABLE).update(
        {"data_registro": None, "origem": "confirmado", "confirmado_por": "u-1"}
    ).eq("id", linha["id"]).execute()
    assert detalhes_svc.rederivar_do_documento(scoped, ORG, doc_id) == 0
    assert _linha(scoped, ext)["data_registro"] is None
