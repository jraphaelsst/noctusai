"""R5 real-deal replay (2026-10-23): a venda e compra that only REFERENCES a
prior cessão stays a venda e compra (so the back-referenced donors resolve to
ITS adquirentes), and a título pointer into a removed documento heals (machine)
or raises a pendência (human). EVERY name and number is invented; only the
LAYOUT is real."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from tests.modules.imovel_hub.conftest import dados_row
from tests.modules.matriculas.conftest import (
    CODIGO, ORG_ID, documento_row, extracao_row, registry_row, seed,
)

from app.modules.matriculas import ato_detalhes_service as detalhes_svc
from app.modules.matriculas import estrutura_service as svc
from app.modules.matriculas import titulo_service

ORG = UUID(ORG_ID)
HOJE = date(2026, 10, 23)

CABECA = "MATRÍCULA Nº 21.748\nFICHA 01\nIMÓVEL: Casa ficticia da Rua dos Exemplos.\nPROPRIETÁRIOS: FULANO ORIGEM EXEMPLO e sua mulher FULANA ORIGEM EXEMPLO.\n"
AV1 = (
    "AV. 01/21.748 - Em 10 de março de 1.980. Averba-se o compromisso de venda e compra "
    "firmado entre os proprietários e EDUARDO ALVORADA EXEMPLO e sua mulher FERNANDA "
    "ALVORADA EXEMPLO.\n"
)
AV2 = (
    "AV.2/ 21.748 - BARUERI, 15 de janeiro de 1985. Pela escritura pública lavrada aos "
    "28/12/84, às fls. 396/399, do livro 198, nas notas do Tabelião de Carapicuiba, desta "
    "comarca, os compromissários compradores, EDUARDO ALVORADA EXEMPLO,- RG. 5.002.617 e "
    "CIC/MF. nº 663.268.778/49, brasileiro, engenheiro, e sua mulher FERNANDA ALVORADA "
    "EXEMPLO, RG. sob nº 5.385.920-SP e CIC/MF. nº 769.754.878/04, brasileira,- "
    "pedagoga, casados no regime da comunhão de bens, antes da Lei nº 6515/77, residentes "
    "na Rua Exemplo, 10, CEDERAM E TRANS- FERIRAM todos os seus direitos e obrigações "
    "decorrentes do compromisso de venda e compra, averbado sob o nº 01, retro, à CICRANO "
    "ADQUIRENTE EXEMPLO, RG 1.111.111 brasileiro, engenheiro, casado no regime da comunhão "
    "de bens, antes da Lei 6515/77, com a senhora BELTRANA ADQUIRENTE EXEMPLO, brasileira, "
    "pedagoga.\n"
)
R3 = (
    "R.3/ 21.748 - BARUERI, 15 de janeiro de 1985. Pela mesma escritura mencionada na "
    "averbação nº 02, acima,- os proprietários FULANO ORIGEM EXEMPLO, e sua mulher FULANA "
    "ORIGEM EXEMPLO, retro qualificados, TRANSMITIRAM definitivamente, por venda e compra, "
    "o imóvel desta matrícula, à CICRANO ADQUIRENTE EXEMPLO, casado com BELTRANA ADQUIRENTE "
    "EXEMPLO, supra qualificados pelo preço ajustado de CR$ 10.000.000, com as condições da "
    "escritura, ficando cumprido e sem mais efeito o compromisso objeto da averbação nº 01, "
    "e por consequência a cessão de direitos objeto da averbação nº 02, supra.\n"
)
R4 = (
    "R. 04/21.748 - Em 12 de fevereiro de 1.988. Por escritura pública, lavra-\nda aos "
    "28/01/1.988, Lº 1058, fls. 279, do 26º Tabelionato de Notas de São Paulo,Capital, os "
    "proprietários retro nomeados e quali-\nficados, transmitiram, a titulo de DOAÇÃO, o "
    "imóvel desta matrícula, à ANA BETA FICTICIA, brasileira, menor, em adiantamento de -\n"
    "legítima.\n"
)
TEXTO = CABECA + AV1 + AV2 + R3 + R4


def _linhas(scoped, ext):
    atos = svc.atos_da_extracao(scoped, ORG, ext)
    det = detalhes_svc.detalhes_por_ato(scoped, ORG, ext, atos)
    return {f"{a['kind']}-{a.get('numero')}": det[str(a["id"])] for a in atos if str(a["id"]) in det}


def test_r5_1_chain_resolves_the_donors_to_the_last_buyers(client, scoped):
    ext = extracao_row(texto=TEXTO)
    seed(scoped, registry=[registry_row()], extracoes=[ext])

    det = _linhas(scoped, ext)
    assert det["AV-2"]["natureza"] == "cessao_direitos"
    assert [p["nome"] for p in det["AV-2"]["transmitentes"]] == [
        "EDUARDO ALVORADA EXEMPLO", "FERNANDA ALVORADA EXEMPLO",
    ]
    assert det["R-3"]["natureza"] == "compra_e_venda"
    assert [p["nome"] for p in det["R-3"]["adquirentes"]] == [
        "CICRANO ADQUIRENTE EXEMPLO", "BELTRANA ADQUIRENTE EXEMPLO",
    ]
    antigos = titulo_service.antigos_proprietarios(scoped, ORG, CODIGO, hoje=HOJE)
    assert antigos["ultima_transferencia"]["ato_ref"] == "R-4"
    assert [t["nome"] for t in antigos["transmitentes"]] == [
        "CICRANO ADQUIRENTE EXEMPLO", "BELTRANA ADQUIRENTE EXEMPLO",
    ]


def _com_ponteiro_morto(scoped, **dados):
    vivo, morto = documento_row(), documento_row()
    morto["deleted_at"] = "2026-10-22T10:00:00+00:00"
    e_vivo = extracao_row(texto=TEXTO, imovel_documento_id=vivo["id"])
    e_morto = extracao_row(texto=TEXTO, imovel_documento_id=morto["id"])
    seed(scoped, registry=[registry_row()], extracoes=[e_vivo, e_morto], documentos=[vivo, morto])
    ato_morto = next(a for a in svc.atos_da_extracao(scoped, ORG, e_morto) if a["kind"] == "R" and a["numero"] == 4)
    scoped.set_table_data("imovel_dados", [dados_row(
        titulo_aquisitivo_extracao_id=e_morto["id"], titulo_aquisitivo_ato_id=ato_morto["id"],
        titulo_aquisitivo_char_inicio=int(ato_morto["char_inicio"]),
        titulo_aquisitivo_char_fim=int(ato_morto["char_fim"]), **dados,
    )])
    return e_vivo, e_morto


def test_r5_3_a_machine_pointer_into_a_removed_documento_heals_in_place(client, scoped):
    e_vivo, _ = _com_ponteiro_morto(
        scoped, titulo_aquisitivo_origem="sugerido", titulo_aquisitivo_confirmado_por=None,
    )

    out = titulo_service.obter_titulo(scoped, ORG, CODIGO)

    assert out["motivo_sem_sugestao"] is None
    assert out["ato"]["extracao_id"] == e_vivo["id"] and out["ato"]["ato_ref"] == "R-4"
    assert out["sugestao"]
    linha = scoped.table("imovel_dados").select("*").execute().data[0]
    assert linha["titulo_aquisitivo_extracao_id"] == e_vivo["id"]


def test_r5_3_a_human_pointer_into_a_removed_documento_raises_a_pendencia(client, scoped):
    e_vivo, e_morto = _com_ponteiro_morto(
        scoped, titulo_aquisitivo_origem="manual", titulo_aquisitivo_confirmado_por="u-1",
    )

    out = titulo_service.obter_titulo(scoped, ORG, CODIGO)

    assert out["motivo_sem_sugestao"] == titulo_service.MOTIVO_MATRICULA_REMOVIDA
    assert "removida" in out["mensagem_pendencia"] and "escolha outra" in out["mensagem_pendencia"]
    assert out["sugestao"] is None and out["ato"] is None
    linha = scoped.table("imovel_dados").select("*").execute().data[0]
    assert linha["titulo_aquisitivo_extracao_id"] == e_morto["id"]  # never swapped
