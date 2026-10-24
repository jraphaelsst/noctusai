"""R4 real-deal replay (2026-10-23): name wraps healed on re-derive and normalised
on read, the escritura date behind a typed wrap, a spouse co-owner under
comunhão universal resolved through the chain, and a cession of promise
rights that is never the last transfer. EVERY name and number is invented;
only the LAYOUT is real."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from tests.modules.matriculas.conftest import CODIGO, ORG_ID, extracao_row, registry_row, seed

from app.modules.matriculas import ato_detalhes_service as detalhes_svc
from app.modules.matriculas import estrutura_service as svc
from app.modules.matriculas import titulo_service

ORG = UUID(ORG_ID)
HOJE = date(2026, 10, 23)

CABECA = "MATRÍCULA Nº 21.748\nFICHA 01\nIMÓVEL: Casa ficticia da Rua dos Exemplos.\n"

AV2 = (
    "AV. 02/21.748 - Em 05 de maio de 1.975. Averba-se que MARCOS ANTONIO EXEMPLO, "
    "brasileiro, engenheiro, casado no regime da comunhão de bens, antes da Lei 6515/77, "
    "com a senhora JOANA MARIA EXEMPLO, brasileira, do lar, residentes em Barueri.\n"
)
R3 = (
    "R. 03/21.748 - Em 10 de março de 1.985. Os proprietários FULANO ORIGEM EXEMPLO e sua "
    "mulher FULANA ORIGEM EXEMPLO TRANSMITIRAM definitivamente, por venda e compra, o "
    "imóvel desta matrícula, à MARCOS ANTONIO EXEMPLO, casado com JOANA MARIA EXEMPLO, "
    "supra qualificados pelo preço de CZ$ 10.000,00.\n"
)
R4 = (
    "R. 04/21.748 - Em 12 de fevereiro de 1.988. Por escritura pública, lavra-\nda aos "
    "28/01/1.988, Lº 1058, fls. 279, do 26º Tabelionato de Notas de São Paulo,Capital, os "
    "proprietários retro nomeados e quali-\nficados, transmitiram, a titulo de DOAÇÃO, o "
    "imóvel desta matrícula, à ANA BETA FICTICIA, brasileira, menor, em adiantamento de -\n"
    "legítima.\n"
)


def _seed(scoped, texto):
    ext = extracao_row(texto=texto)
    seed(scoped, registry=[registry_row()], extracoes=[ext])
    return ext


def _linhas(scoped, ext):
    atos = svc.atos_da_extracao(scoped, ORG, ext)
    det = detalhes_svc.detalhes_por_ato(scoped, ORG, ext, atos)
    return {f"{a['kind']}-{a.get('numero')}": det[str(a["id"])] for a in atos if str(a["id"]) in det}


def test_f69_back_referenced_sellers_resolve_to_both_spouses(client, scoped):
    ext = _seed(scoped, CABECA + AV2 + R3 + R4)

    det = _linhas(scoped, ext)
    assert [p["nome"] for p in det["R-3"]["adquirentes"]] == [
        "MARCOS ANTONIO EXEMPLO", "JOANA MARIA EXEMPLO",
    ]
    antigos = titulo_service.antigos_proprietarios(scoped, ORG, CODIGO, hoje=HOJE)
    assert [t["nome"] for t in antigos["transmitentes"]] == [
        "MARCOS ANTONIO EXEMPLO", "JOANA MARIA EXEMPLO",
    ]


def test_f69_comunhao_parcial_resolves_only_the_named_buyer(client, scoped):
    texto = CABECA + AV2.replace("comunhão de bens, antes da Lei 6515/77", "comunhão parcial de bens") + R3 + R4
    ext = _seed(scoped, texto)

    assert [p["nome"] for p in _linhas(scoped, ext)["R-3"]["adquirentes"]] == ["MARCOS ANTONIO EXEMPLO"]
    antigos = titulo_service.antigos_proprietarios(scoped, ORG, CODIGO, hoje=HOJE)
    assert [t["nome"] for t in antigos["transmitentes"]] == ["MARCOS ANTONIO EXEMPLO"]


def test_f68_the_titulo_phrase_carries_the_escritura_date_behind_a_wrap(client, scoped):
    ext = _seed(scoped, CABECA + AV2 + R3 + R4)
    det = _linhas(scoped, ext)
    assert det["R-4"]["instrumento"]["data"] == "1988-01-28"

    from app.modules.matriculas import cadeia_dominial

    ato = next(a for a in svc.atos_da_extracao(scoped, ORG, ext) if a["kind"] == "R" and a["numero"] == 4)
    frase = cadeia_dominial.frase_titulo(ato, det["R-4"])
    assert "lavrada em 28/01/1988" in frase


def test_f67_stored_wrapped_names_heal_on_rederive_and_show_clean(client, scoped):
    ext = _seed(scoped, CABECA + R3.replace("à MARCOS ANTONIO EXEMPLO, casado com JOANA MARIA EXEMPLO,", "à MARCOS ANTONIO MONTEIRO CEZAR,") + R4)
    linha = _linhas(scoped, ext)["R-3"]
    scoped.table(detalhes_svc.DETALHES_TABLE).update(
        {"adquirentes": [{"nome": "MARCOS ANTONIO MONTEIRO CE--\nZAR", "cpf_cnpj": None}]}
    ).eq("id", linha["id"]).execute()

    nova = _linhas(scoped, ext)["R-3"]

    assert [p["nome"] for p in nova["adquirentes"]] == ["MARCOS ANTONIO MONTEIRO CEZAR"]


def test_f67_a_human_row_is_shown_normalised_but_never_rewritten(client, scoped):
    ext = _seed(scoped, CABECA + R3 + R4)
    linha = _linhas(scoped, ext)["R-3"]
    bruto = [{"nome": "THIAGO LUIS KISS\nCEZAR", "cpf_cnpj": None}]
    scoped.table(detalhes_svc.DETALHES_TABLE).update(
        {"adquirentes": bruto, "origem": "confirmado", "confirmado_por": "u-1"}
    ).eq("id", linha["id"]).execute()

    stored = _linhas(scoped, ext)["R-3"]
    saida = detalhes_svc.detalhes_saida(stored, {})

    assert stored["adquirentes"] == bruto  # a human's row is never touched
    assert [p["nome"] for p in saida["adquirentes"]] == ["THIAGO LUIS KISS CEZAR"]


CESSAO = (
    "AV. 05/21.748 - Em 05 de maio de 1.990. Averba-se que, por instrumento particular de "
    "02/05/1990, os compromissários compradores, MARCOS ANTONIO EXEMPLO,- RG nº "
    "11.111.111-SSP/SP, brasileiro, engenheiro, e sua mulher JOANA MARIA EXEMPLO, RG nº "
    "22.222.222-SSP/SP, brasileira,-\npedagoga, casados pelo regime da comunhão de bens, "
    "CEDERAM E TRANS-\nFERIRAM todos os seus direitos e obrigações decorrentes do "
    "compromisso de compra e venda registrado sob nº R.1, à PAULO ROBERTO FICTICIO, RG "
    "33.333.333, brasileiro, solteiro, comerciante.\n"
)


def test_f70_a_cession_is_typed_and_is_not_the_last_transfer(client, scoped):
    ext = _seed(scoped, CABECA + AV2 + R3 + R4 + CESSAO)

    det = _linhas(scoped, ext)["AV-5"]
    assert det["natureza"] == "cessao_direitos"
    assert [p["nome"] for p in det["transmitentes"]] == ["MARCOS ANTONIO EXEMPLO", "JOANA MARIA EXEMPLO"]
    assert [p["nome"] for p in det["adquirentes"]] == ["PAULO ROBERTO FICTICIO"]

    antigos = titulo_service.antigos_proprietarios(scoped, ORG, CODIGO, hoje=HOJE)
    assert antigos["ultima_transferencia"]["ato_ref"] == "R-4"  # the cession is after, yet not it
    assert antigos["ultima_transferencia"]["natureza"] == "doacao"


def test_f70_a_stored_outro_with_a_profession_as_name_is_rederived(client, scoped):
    ext = _seed(scoped, CABECA + AV2 + R3 + CESSAO)
    linha = _linhas(scoped, ext)["AV-5"]
    scoped.table(detalhes_svc.DETALHES_TABLE).update(
        {
            "natureza": "outro",
            "natureza_confianca": "baixa",
            "transmitentes": [{"nome": "pedagoga", "cpf_cnpj": None}],
        }
    ).eq("id", linha["id"]).execute()

    nova = _linhas(scoped, ext)["AV-5"]

    assert nova["natureza"] == "cessao_direitos"
    assert [p["nome"] for p in nova["transmitentes"]] == ["MARCOS ANTONIO EXEMPLO", "JOANA MARIA EXEMPLO"]
