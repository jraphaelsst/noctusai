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


def test_chain_titularidade_reads_all_donatarios_of_the_doacao(client, scoped):
    texto = (
        "MATRÍCULA Nº 21.748\nFICHA 01\nIMÓVEL: Casa ficticia da Rua dos Exemplos.\n"
        "R-4/21.748 - Em 12/02/1988. DOAÇÃO. Os proprietários FULANO ORIGEM EXEMPLO e sua "
        "mulher FULANA ORIGEM EXEMPLO, transmitiram, a titulo de DOAÇÃO, o imóvel desta--\n"
        "matricula, à ANA QUARTA FICTICIA, nascido aos 31/10/77,\nBRUNO QUARTO FICTICIO , "
        "nascido aos 19/09/79, e CARLA QUARTA FICTICIA, nascido aos 28/04/1.981, todos "
        "brasileiros, menores\nimpúberes, representados por seus\npais, os doadores, supra "
        "qualificados em adiantamento de -\nlegítima.\n"
    )
    seed(scoped, registry=[registry_row()], extracoes=[extracao_row(texto=texto)])

    out = titulo_service.titularidade_atual(scoped, ORG, CODIGO)
    assert [p["nome"] for p in out["proprietarios"]] == [
        "ANA QUARTA FICTICIA", "BRUNO QUARTO FICTICIO", "CARLA QUARTA FICTICIA",
    ]
    antigos = titulo_service.antigos_proprietarios(scoped, ORG, CODIGO, hoje=date(2026, 10, 23))
    assert [t["nome"] for t in antigos["transmitentes"]] == [
        "FULANO ORIGEM EXEMPLO", "FULANA ORIGEM EXEMPLO",
    ]


def test_rederive_never_downgrades_a_machine_suggestion(client, scoped):
    """A value the current parser cannot reproduce stays; a different non-null
    parse replaces; junk names go."""
    ext = _extracao(scoped)
    linha = _linha(scoped, ext)
    scoped.table(detalhes_svc.DETALHES_TABLE).update(
        {
            "credor": "BANCO FICTICIO S.A.",
            "credor_confianca": "alta",
            "data_registro": "1999-09-09",
            "adquirentes": [{"nome": "brasileira", "cpf_cnpj": None}],
        }
    ).eq("id", linha["id"]).execute()

    nova = _linha(scoped, ext)

    assert nova["credor"] == "BANCO FICTICIO S.A."  # parser finds none: kept
    assert str(nova["data_registro"])[:10] == "1988-02-12"  # different non-null parse
    assert [p["nome"] for p in nova["adquirentes"]] == ["ANA QUARTA FICTICIA"]


def test_rederivar_do_imovel_heals_old_parser_rows_and_spares_confirmed(client, scoped):
    """F104: an extraction minted by the old parser (adquirente lost to a page
    break) heals on the sync path; a confirmed qualificação is never touched."""
    from app.modules.matriculas import qualificacao_service as qsvc
    from tests.modules.matriculas.test_qualificacao import CPF_CAMILA, CPF_JOSE

    texto = (
        "MATRÍCULA Nº 90.222 — FICHA 01\nIMÓVEL: Casa ficticia da Rua dos Exemplos.\n"
        "R-1/90.222 - Em 10/05/2021. VENDA E COMPRA. A proprietária EMPRESA EXEMPLO "
        "LTDA, já qualificada, transmitiu o\n\ncontinua no verso\n\nMOD. 10\n\n"
        "imóvel desta matrícula a JOSÉ EXEMPLO LIMA, brasileiro, divorciado, piloto, "
        f"RG nº 11.222.333-4-SSP/SP, CPF nº {CPF_JOSE}, residente na Rua Um, 10.\n"
        "R-2/90.222 - Em 10/03/2023. VENDA. JOSÉ EXEMPLO LIMA, já qualificado, vendeu "
        "o imóvel a CAMILA EXEMPLO BRITO, brasileira, solteira, arquiteta, RG nº "
        f"66.777.888-SSP/SP, CPF nº {CPF_CAMILA}, residente na Avenida Modelo, 90.\n"
    )
    ext = extracao_row(texto=texto)
    seed(scoped, registry=[registry_row()], extracoes=[ext])
    atos = svc.atos_da_extracao(scoped, ORG, ext)
    detalhes_svc.detalhes_por_ato(scoped, ORG, ext, atos)
    qsvc.qualificacoes_da_extracao(scoped, ORG, ext, atos)

    # Simulate the OLD parser: José's qualificação missing, R-2's seller bare;
    # Camila's row confirmed by a human with a different profissão.
    rows = scoped.table("matricula_qualificacoes").select("*").execute().data
    camila = next(r for r in rows if r["cpf_cnpj"] == CPF_CAMILA)
    scoped.set_table_data("matricula_qualificacoes", [camila])
    scoped.table("matricula_qualificacoes").update(
        {"profissao": "pintora", "confirmado_em": "2026-10-01T00:00:00+00:00", "confirmado_por": "u-1"}
    ).eq("id", camila["id"]).execute()
    r2 = next(a for a in atos if a["numero"] == 2)
    scoped.table(detalhes_svc.DETALHES_TABLE).update(
        {"transmitentes": [{"nome": "JOSÉ EXEMPLO LIMA", "cpf_cnpj": None}], "origem": "sugestao"}
    ).eq("ato_id", str(r2["id"])).execute()

    detalhes_svc.rederivar_do_imovel(scoped, ORG, CODIGO)

    qs = {r["cpf_cnpj"]: r for r in scoped.table("matricula_qualificacoes").select("*").execute().data}
    assert qs[CPF_JOSE]["estado_civil"] == "divorciado"
    assert qs[CPF_CAMILA]["profissao"] == "pintora"  # confirmed row untouched
    linha = _linha_do_ato(scoped, ext, 2)
    assert linha["transmitentes"][0]["cpf_cnpj"] == CPF_JOSE


def _linha_do_ato(scoped, ext, numero):
    atos = svc.atos_da_extracao(scoped, ORG, ext)
    det = detalhes_svc.detalhes_por_ato(scoped, ORG, ext, atos)
    ato = next(a for a in atos if a["numero"] == numero)
    return det[str(ato["id"])]
