"""F62/F63/F64 (real-deal replay, 2026-10-23): a doação on a CLOSED predecessor
matrícula typed on a 1988 page (OCR line wraps, dotted years, hyphen wraps), an
ONR heading whose cartório is cut by a line break, and stale conflict rows.
EVERY name, number and registry below is invented; only the LAYOUT is real."""
from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from tests.modules.matriculas.conftest import (
    CODIGO,
    ORG_ID,
    documento_row,
    extracao_row,
    registry_row,
    seed,
)

from app.modules.imovel_hub import campos_extraidos_service as campos_svc
from app.modules.imovel_hub import dados_service
from app.modules.matriculas import cadeia_dominial, preenchimento_service as preench, titulo_service

ORG = UUID(ORG_ID)

ATUAL = (
    "OFICIAL DE REGISTRO DE IMÓVEIS\nDA COMARCA DE CARAPICUÍBA/SP\nMATRÍCULA Nº 11.926\nFICHA 01\n"
    "IMÓVEL: Casa ficticia da Rua dos Exemplos.\n"
    "REGISTRO ANTERIOR: R-04/M-21.748 de 12/02/1.988, do Registro de Imóveis de Barueri/SP.\n"
    "AV-01/11.926 - Em 10/03/2014. Averba-se a abertura desta matrícula.\n"
)

ANTERIOR = (
    "CARTÓRIO DE REGISTRO DE IMÓVEIS DE\n\nBARUERI -SP.\n\nMATRÍCULA\n- 21748\n\n"
    "IMÓVEL: Casa ficticia da Rua dos Exemplos.\n"
    "R. 04/ 21.748 .-          Barueri, 12 de fevereiro de 1.988 .-\n"
    "Por escritura pública, lavrada aos 28/\n"
    "01/1.988, Lº 1058, fls. 279, do 26º Tabelionato de Notas de\n"
    "São Paulo,Capital, os proprietários retro nomeados e quali-\n"
    "ficados, transmitiram, a titulo de DOAÇÃO, o imóvel desta--\n"
    "matricula, à ANA BETA FICTICIA, nascido aos .., BRUNO BETA FICTICIO ..., e CLARA BETA "
    "FICTICIA, ..., todos brasileiros, menores\n"
    "impúberes, ..., nêste ato representados por seus\n"
    "pais, os doadores, supra qualificados em adiantamento de -\n"
    "legítima, nos têrmos do artº 1.171, do C.C.Brasileiro,Valor\n"
    "CZ$  42.270.22.\n"
    "Av. 05/21.748, em 02 de janeiro de 2.018. Averba-se: b) que o imóvel objeto desta se "
    "encontra atualmente matriculado sob nº 11.926 no\n"
    "Registro de Imóveis de Carapicuíba, deste Estado, ficando consequentemente\n"
    "encerrada a presente matrícula.\n"
)

ORIGEM = (
    "da matrícula nº 21.748 do Cartório de Registro de Imóveis de Barueri/SP, atualmente "
    "matriculado sob o nº 11.926 do Oficial de Registro de Imóveis da Comarca de Carapicuíba/SP"
)


def _cenario(scoped, *, flag_encerrada=True):
    doc_atual, doc_ant = documento_row(), documento_row()
    doc_ant["matricula_encerrada"] = flag_encerrada
    doc_ant["matriculada_sob"] = "11926" if flag_encerrada else None
    atual = extracao_row(texto=ATUAL, imovel_documento_id=doc_atual["id"])
    atual["created_at"] = "2026-02-01T00:00:00+00:00"
    anterior = extracao_row(texto=ANTERIOR, imovel_documento_id=doc_ant["id"])
    anterior["created_at"] = "2026-03-01T00:00:00+00:00"
    seed(
        scoped,
        registry=[registry_row()],
        extracoes=[atual, anterior],
        documentos=[doc_atual, doc_ant],
    )
    return atual, anterior


def test_f63_the_predecessor_cartorio_is_joined_across_the_line_break(scoped):
    _atual, anterior = _cenario(scoped)
    origem = cadeia_dominial.matricula_origem(scoped, ORG, anterior)
    assert origem == ORIGEM
    assert not origem.split(" do ")[1].endswith(" DE")


def test_f63_a_closed_predecessor_never_proposes_the_current_registry(scoped):
    atual, anterior = _cenario(scoped, flag_encerrada=False)  # recognised from its text
    preench.preencher_sincrono(scoped, ORG_ID, atual["id"])

    resumo, conflitos = preench.preencher_sincrono(scoped, ORG_ID, anterior["id"])

    assert resumo.get("predecessora") is True and conflitos == []
    linha = dados_service.linha(scoped, ORG, CODIGO)
    assert linha["numero_registro_imoveis"] == "OFICIAL DE REGISTRO DE IMÓVEIS DA COMARCA DE CARAPICUÍBA/SP"
    assert linha["numero_matricula"] == "11.926"


def test_f64_the_titulo_phrase_and_the_last_transfer_carry_every_fact(scoped):
    atual, anterior = _cenario(scoped)

    preench.preencher_sincrono(scoped, ORG_ID, atual["id"])

    linha = dados_service.linha(scoped, ORG, CODIGO)
    assert linha["titulo_aquisitivo_extracao_id"] == anterior["id"]
    assert linha["titulo_aquisitivo_texto"] == (
        "por escritura pública de doação, em adiantamento de legítima, lavrada em "
        "28/01/1988 no 26º Tabelionato de Notas de São Paulo/SP, Livro 1058, fls. 279, "
        f"registrada sob o R-4 em 12/02/1988 {ORIGEM}"
    )
    ult = titulo_service.antigos_proprietarios(scoped, ORG, CODIGO, hoje=date(2026, 10, 23))[
        "ultima_transferencia"
    ]
    assert ult["ato_ref"] == "R-4" and ult["natureza"] == "doacao"
    assert ult["data_registro"] == "1988-02-12"
    assert ult["matricula_origem"] == ORIGEM


def _conflito(campo, *, anterior, proposto, fonte_id=None, created="2026-10-01T00:00:00+00:00"):
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "codigo": CODIGO, "campo": campo,
        "valor_anterior": anterior, "origem_anterior": "manual",
        "valor_proposto": proposto, "origem_proposto": "matricula",
        "fonte_tabela": "matricula_extracoes" if fonte_id else None, "fonte_id": fonte_id,
        "documento_id_proposto": None, "status": "pendente", "decidido_por": None,
        "created_at": created,
    }


def _linhas(scoped):
    return {c["id"]: c for c in scoped.table("imovel_campo_conflitos").select("*").execute().data}


def test_f62_clearing_a_field_resolves_its_pending_conflicts(scoped):
    from tests.modules.imovel_hub.conftest import dados_row

    seed(scoped, registry=[registry_row()])
    scoped.set_table_data("imovel_dados", [dados_row(
        titulo_aquisitivo_texto="texto antigo", titulo_aquisitivo_texto_origem="manual",
    )])
    c = _conflito("titulo_aquisitivo_texto", anterior="texto antigo", proposto="texto novo")
    outro = _conflito("numero_matricula", anterior="1", proposto="2")
    scoped.set_table_data("imovel_campo_conflitos", [c, outro])

    titulo_service.confirmar_titulo(scoped, ORG, CODIGO, texto=None, usuario_id=None)

    linhas = _linhas(scoped)
    assert linhas[c["id"]]["status"] == "resolvido_automatico"
    assert linhas[c["id"]]["motivo_resolucao"].startswith("[campo_limpo]")
    assert linhas[outro["id"]]["status"] == "pendente"  # another field: untouched


def test_f62_a_newer_extraction_of_the_same_document_supersedes_old_proposals(scoped):
    doc = documento_row()
    velha = extracao_row(texto=ATUAL, imovel_documento_id=doc["id"])
    velha["created_at"] = "2026-02-01T00:00:00+00:00"
    nova = extracao_row(texto=ATUAL, imovel_documento_id=doc["id"])
    nova["created_at"] = "2026-03-01T00:00:00+00:00"
    seed(scoped, registry=[registry_row()], extracoes=[velha, nova], documentos=[doc])
    from tests.modules.imovel_hub.conftest import dados_row

    scoped.set_table_data("imovel_dados", [dados_row(numero_matricula="11.926")])
    stale = _conflito("numero_matricula", anterior="11.926", proposto="99", fonte_id=velha["id"])
    viva = _conflito("numero_registro_imoveis", anterior="A", proposto="B", fonte_id=nova["id"])
    scoped.set_table_data("imovel_campo_conflitos", [stale, viva])

    campos_svc.backfill_resolver_conflitos_pendentes(scoped, ORG, codigo=CODIGO)

    linhas = _linhas(scoped)
    assert linhas[stale["id"]]["status"] == "resolvido_automatico"
    assert linhas[stale["id"]]["motivo_resolucao"].startswith("[substituido]")
    assert linhas[viva["id"]]["status"] != "resolvido_automatico" or "[substituido]" not in (
        linhas[viva["id"]].get("motivo_resolucao") or ""
    )


def test_f62_a_proposal_from_what_is_now_a_closed_predecessor_is_retired(scoped):
    from tests.modules.imovel_hub.conftest import dados_row

    atual, anterior = _cenario(scoped)
    scoped.set_table_data("imovel_dados", [dados_row(
        numero_registro_imoveis="OFICIAL DE REGISTRO DE IMÓVEIS DA COMARCA DE CARAPICUÍBA/SP"
    )])
    c = _conflito(
        "numero_registro_imoveis",
        anterior="OFICIAL DE REGISTRO DE IMÓVEIS DA COMARCA DE CARAPICUÍBA/SP",
        proposto="CARTÓRIO DE REGISTRO DE IMÓVEIS DE", fonte_id=anterior["id"],
    )
    scoped.set_table_data("imovel_campo_conflitos", [c])

    campos_svc.backfill_resolver_conflitos_pendentes(scoped, ORG, codigo=CODIGO)

    assert _linhas(scoped)[c["id"]]["motivo_resolucao"].startswith("[predecessora]")
