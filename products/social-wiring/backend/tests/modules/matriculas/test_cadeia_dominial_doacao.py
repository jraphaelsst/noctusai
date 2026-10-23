"""A doação on a CLOSED predecessor matrícula is the imóvel's last transfer
and its título aquisitivo (owner 2026-10-22). Synthetic data only."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from tests.modules.matriculas.conftest import (
    CODIGO,
    ORG_ID,
    documento_row,
    extracao_row,
    registry_row,
    seed,
)

from app.modules.matriculas import cadeia_dominial, titulo_service

ORG = UUID(ORG_ID)

ATUAL = (
    "OFICIAL DE REGISTRO DE IMÓVEIS\nDA COMARCA DE CARAPICUÍBA/SP\nMATRÍCULA Nº 11.926\nFICHA 01\n"
    "IMÓVEL: Casa ficticia da Rua dos Exemplos.\n"
    "REGISTRO ANTERIOR: R-04/M-21.748 do Registro de Imóveis de Barueri/SP.\n"
    "AV-01/11.926 - Em 10/03/2014. Averba-se a abertura desta matrícula.\n"
)

ANTERIOR = (
    "1º OFICIAL DE REGISTRO DE IMÓVEIS DE BARUERI/SP\nMATRÍCULA Nº 21.748\nFICHA 01\n"
    "IMÓVEL: Casa ficticia da Rua dos Exemplos.\n"
    "R-3/21.748 - Em 15/01/1985. COMPRA E VENDA. Transmitente: JOSE PRIMEIRO FICTICIO, "
    "CPF 246.813.579-28; adquirente: MARCOS SEGUNDO FICTICIO, CPF 135.792.468-28.\n"
    "R-4/21.748 - Em 12/02/1988. Por escritura pública, lavrada aos 28/01/1988, Lº 1058, "
    "fls. 279, do 26º Tabelionato de Notas de São Paulo - SP, os proprietários MARCOS "
    "SEGUNDO FICTICIO, CPF 135.792.468-28 e sua mulher MARIA TERCEIRA FICTICIA, CPF "
    "314.159.265-90, transmitiram, a título de DOAÇÃO, o imóvel objeto desta matrícula, a "
    "ANA QUARTA FICTICIA, BRUNO QUARTO FICTICIO, menores impúberes, representados por seus "
    "pais, os doadores, em adiantamento de legítima.\n"
    "AV-5/21.748 - Em 20/03/2014. Fica encerrada a presente matrícula, por ter o imóvel "
    "sido matriculado sob nº 11.926 no Registro de Imóveis de Carapicuíba/SP.\n"
)


def _cenario(scoped):
    doc_atual = documento_row()
    doc_ant = documento_row()
    doc_ant["matricula_encerrada"] = True
    doc_ant["matriculada_sob"] = "11926"
    atual = extracao_row(texto=ATUAL, imovel_documento_id=doc_atual["id"])
    atual["created_at"] = "2026-02-01T00:00:00+00:00"
    anterior = extracao_row(texto=ANTERIOR, imovel_documento_id=doc_ant["id"])
    anterior["created_at"] = "2026-03-01T00:00:00+00:00"  # uploaded LAST
    seed(
        scoped,
        registry=[registry_row()],
        extracoes=[atual, anterior],
        documentos=[doc_atual, doc_ant],
    )
    return atual, anterior


def test_the_last_transfer_is_the_doacao_on_the_closed_predecessor(client, scoped):
    atual, anterior = _cenario(scoped)

    out = titulo_service.antigos_proprietarios(scoped, ORG, CODIGO, hoje=date(2026, 10, 22))

    ult = out["ultima_transferencia"]
    assert ult["ato_ref"] == "R-4" and ult["natureza"] == "doacao"
    assert ult["data_registro"] == "1988-02-12"
    assert ult["extracao_id"] == anterior["id"]
    assert ult["matricula_origem"] == (
        "da matrícula nº 21.748 do 1º Oficial de Registro de Imóveis de Barueri/SP, "
        "atualmente matriculado sob o nº 11.926 do Oficial de Registro de Imóveis da "
        "Comarca de Carapicuíba/SP"
    )
    assert out["origem"] == "matricula_anterior"
    assert [t["nome"] for t in out["transmitentes"]][:1] == ["MARCOS SEGUNDO FICTICIO"]
    assert out["exige_certidoes"] is False  # 1988


def test_the_predecessor_never_becomes_the_current_extraction(client, scoped):
    atual, anterior = _cenario(scoped)
    assert cadeia_dominial.extracao_e_predecessora(scoped, ORG, anterior)
    assert not cadeia_dominial.extracao_e_predecessora(scoped, ORG, atual)
    assert [e["id"] for e in cadeia_dominial.extracoes_predecessoras(scoped, ORG, CODIGO)] == [
        anterior["id"]
    ]


def test_the_titulo_phrase_carries_every_fact_of_the_doacao(client, scoped):
    _atual, anterior = _cenario(scoped)
    atos = client.get(f"/api/matriculas/extracoes/{anterior['id']}/atos").json()["data"]["atos"]
    r4 = next(a for a in atos if a["kind"] == "R" and a["numero"] == 4)

    from app.modules.matriculas import ato_detalhes_service as detalhes_svc, estrutura_service

    ext = estrutura_service.exigir_extracao(scoped, ORG, anterior["id"])
    lista = estrutura_service.atos_da_extracao(scoped, ORG, ext)
    det = detalhes_svc.detalhes_por_ato(scoped, ORG, ext, lista)[r4["id"]]
    frase = cadeia_dominial.frase_titulo(
        next(a for a in lista if str(a["id"]) == r4["id"]),
        det,
        cadeia_dominial.matricula_origem(scoped, ORG, ext),
    )

    assert frase == (
        "por escritura pública de doação, em adiantamento de legítima, lavrada em "
        "28/01/1988 no 26º Tabelionato de Notas de São Paulo, Livro 1058, fls. 279, "
        "registrada sob o R-4 em 12/02/1988 da matrícula nº 21.748 do 1º Oficial de "
        "Registro de Imóveis de Barueri/SP, atualmente matriculado sob o nº 11.926 do "
        "Oficial de Registro de Imóveis da Comarca de Carapicuíba/SP"
    )


def test_the_current_fill_points_the_titulo_at_the_predecessors_doacao(client, scoped):
    from app.modules.matriculas import preenchimento_service as preench

    atual, anterior = _cenario(scoped)

    resumo, _ = preench.preencher_sincrono(scoped, ORG_ID, atual["id"])

    assert resumo["status"] == "ok"
    linha = [r for r in scoped.table("imovel_dados").select("*").execute().data
             if r["codigo"] == CODIGO][0]
    assert linha["titulo_aquisitivo_extracao_id"] == anterior["id"]
    assert linha["numero_matricula"] == "11.926"
    texto = linha["titulo_aquisitivo_texto"]
    assert "de doação, em adiantamento de legítima," in texto
    assert texto.endswith(
        "do 1º Oficial de Registro de Imóveis de Barueri/SP, atualmente matriculado sob o "
        "nº 11.926 do Oficial de Registro de Imóveis da Comarca de Carapicuíba/SP"
    )
    # The suggestion endpoint says the same thing from the stored pointer.
    out = titulo_service.obter_titulo(scoped, ORG, CODIGO)
    assert out["sugestao"] == texto and out["divergencias"] == []


def test_filling_from_the_predecessor_never_overwrites_the_current_reading(client, scoped):
    from app.modules.matriculas import preenchimento_service as preench

    atual, anterior = _cenario(scoped)
    preench.preencher_sincrono(scoped, ORG_ID, atual["id"])

    resumo, conflitos = preench.preencher_sincrono(scoped, ORG_ID, anterior["id"])

    assert resumo.get("predecessora") is True and conflitos == []
    linha = [r for r in scoped.table("imovel_dados").select("*").execute().data
             if r["codigo"] == CODIGO][0]
    assert linha["numero_matricula"] == "11.926"


def test_predecessor_is_recognised_from_its_text_when_the_document_flag_is_unset(scoped):
    """F60/F61: a closed matrícula never re-read has `matricula_encerrada`
    unset; its transcription's closing averbação is enough."""
    atual, anterior = _cenario(scoped)
    docs = scoped.table("imovel_documentos")
    for linha in docs.select("*").execute().data:
        docs.update({"matricula_encerrada": False, "matriculada_sob": None}).eq(
            "id", linha["id"]
        ).execute()
    assert cadeia_dominial.extracao_e_predecessora(scoped, ORG, anterior) is True
    assert cadeia_dominial.extracao_e_predecessora(scoped, ORG, atual) is False
    assert [e["id"] for e in cadeia_dominial.extracoes_predecessoras(scoped, ORG, CODIGO)] == [
        anterior["id"]
    ]
