"""Real-deal replay R4 (2026-10-23): party-name wraps, the escritura date behind a
typed hyphen wrap, a spouse who co-owns under comunhão universal, and a
cession of promise rights. EVERY name and number is invented; only the LAYOUT
is real."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.integrations.documents import (
    NATUREZAS_ATO,
    NATUREZAS_TRANSFERENCIA,
    extrair_detalhes_ato,
    frase_titulo_aquisitivo,
    nome_de_parte_valido,
    normalizar_nome_parte,
)
from noctusai_lib.integrations.documents.matricula_ato_detalhes import Parte


# ─── F67 · one name normalizer ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("THIAGO LUIS KISS\nCEZAR", "THIAGO LUIS KISS CEZAR"),
        ("MARCOS ANTONIO MONTEIRO CE--\nZAR", "MARCOS ANTONIO MONTEIRO CEZAR"),
        ("MARCOS ANTONIO MONTEIRO CE-\nZAR", "MARCOS ANTONIO MONTEIRO CEZAR"),
        ("MARCOS ANTONIO MONTEIRO CE-- ZAR", "MARCOS ANTONIO MONTEIRO CEZAR"),
        ("ANA   BETA\n  FICTICIA", "ANA BETA FICTICIA"),
        ("MARIA-LUIZA FICTICIA", "MARIA-LUIZA FICTICIA"),  # a real hyphen stays
        ("ANA - BETA", "ANA - BETA"),  # a spaced dash stays
    ],
)
def test_f67_the_single_normalizer(bruto, esperado):
    assert normalizar_nome_parte(bruto) == esperado
    assert Parte(nome=bruto).nome == esperado  # parse side
    assert Parte.from_json({"nome": bruto}).nome == esperado  # read side


def test_f67_parsed_names_never_carry_the_wrap():
    texto = (
        "R-3/21.748 - Em 10 de março de 1985. Por escritura de venda e compra, os "
        "proprietários FULANO ORIGEM EXEMPLO e sua mulher FULANA ORIGEM EXEMPLO "
        "transmitiram o imóvel a %s, brasileiro, pelo preço de CZ$ 10.000,00."
    )
    for bruto, esperado in (
        ("THIAGO LUIS KISS\nCEZAR", "THIAGO LUIS KISS CEZAR"),
        ("MARCOS ANTONIO MONTEIRO CE--\nZAR", "MARCOS ANTONIO MONTEIRO CEZAR"),
    ):
        d = extrair_detalhes_ato(texto % bruto)
        assert [p.nome for p in d.adquirentes] == [esperado]


# ─── F68 · the escritura date behind a typed wrap ──────────────────────────

_DOACAO_QUEBRADA = (
    "R. 04/ 21.748 .-          Barueri, 12 de fevereiro de 1.988 .-\n"
    "Por escritura pública, lavra-\nda aos 28/01/1.988, Lº 1058, fls. 279, do 26º "
    "Tabelionato de Notas de\nSão Paulo,Capital, os proprietários retro nomeados e quali-\n"
    "ficados, transmitiram, a titulo de DOAÇÃO, o imóvel desta--\nmatricula, à ANA BETA "
    "FICTICIA, brasileira, menor, em adiantamento de -\nlegítima.\n"
)


def test_f68_the_date_survives_a_word_wrapped_verb():
    d = extrair_detalhes_ato(_DOACAO_QUEBRADA)
    assert d.instrumento.data == date(1988, 1, 28)
    frase = frase_titulo_aquisitivo(
        d.instrumento, kind="R", numero=4, natureza=d.natureza, uf_origem="SP",
        data_registro=d.data_registro,
    )
    assert "lavrada em 28/01/1988" in frase
    assert frase.startswith("por escritura pública de doação, em adiantamento de legítima, lavrada em")


def test_f68_a_double_hyphen_after_a_complete_word_is_padding_not_a_wrap():
    d = extrair_detalhes_ato(_DOACAO_QUEBRADA)
    assert [p.nome for p in d.adquirentes] == ["ANA BETA FICTICIA"]


# ─── F69 · the spouse co-owns under comunhão universal ─────────────────────

_AV2 = (
    "AV. 02/21.748 - Em 05 de maio de 1.975. Averba-se que MARCOS ANTONIO EXEMPLO, "
    "brasileiro, engenheiro, casado no regime da comunhão de bens, antes da Lei "
    "6515/77, com a senhora JOANA MARIA EXEMPLO, brasileira, do lar, residentes em Barueri.\n"
)
_R3 = (
    "R. 03/21.748 - Em 10 de março de 1.985. Os proprietários FULANO ORIGEM EXEMPLO e "
    "sua mulher FULANA ORIGEM EXEMPLO TRANSMITIRAM definitivamente, por venda e compra, "
    "o imóvel desta matrícula, à MARCOS ANTONIO EXEMPLO, casado com JOANA MARIA EXEMPLO, "
    "supra qualificados pelo preço de CZ$ 10.000,00.\n"
)


def _adq(r3: str, anterior: str) -> list[str]:
    return [p.nome for p in extrair_detalhes_ato(r3, anterior=anterior).adquirentes]


def test_f69_comunhao_de_bens_before_lei_6515_makes_the_spouse_co_adquirente():
    assert _adq(_R3, _AV2) == ["MARCOS ANTONIO EXEMPLO", "JOANA MARIA EXEMPLO"]


def test_f69_comunhao_universal_explicit():
    av2 = _AV2.replace("comunhão de bens, antes da Lei 6515/77", "comunhão universal de bens")
    assert _adq(_R3, av2) == ["MARCOS ANTONIO EXEMPLO", "JOANA MARIA EXEMPLO"]


@pytest.mark.parametrize(
    "regime",
    [
        "comunhão parcial de bens",
        "separação total de bens",
        "comunhão de bens",  # unqualified and NOT placed before Lei 6.515/77: ambiguous
    ],
)
def test_f69_other_regimes_only_the_named_buyer(regime):
    av2 = _AV2.replace("comunhão de bens, antes da Lei 6515/77", regime)
    assert _adq(_R3, av2) == ["MARCOS ANTONIO EXEMPLO"]


def test_f69_no_regime_stated_never_invents_a_co_owner():
    assert _adq(_R3, "") == ["MARCOS ANTONIO EXEMPLO"]


def test_f69_the_regime_of_another_couple_does_not_leak():
    av2 = _AV2.replace("MARCOS ANTONIO EXEMPLO", "OUTRO CASAL EXEMPLO").replace(
        "JOANA MARIA EXEMPLO", "OUTRA CASADA EXEMPLO"
    )
    assert _adq(_R3, av2) == ["MARCOS ANTONIO EXEMPLO"]


def test_f69_a_party_listed_with_e_sua_mulher_is_not_duplicated():
    r3 = _R3.replace("casado com JOANA MARIA EXEMPLO,", "e sua mulher JOANA MARIA EXEMPLO,")
    assert _adq(r3, _AV2) == ["MARCOS ANTONIO EXEMPLO", "JOANA MARIA EXEMPLO"]


# ─── F70 · cessão de direitos do compromisso ───────────────────────────────

_CESSAO = (
    "AV. 02/21.748 - Em 05 de maio de 1.980. Averba-se que, por instrumento particular de "
    "02/05/1980, os compromissários compradores, MARCOS ANTONIO EXEMPLO,- RG nº "
    "11.111.111-SSP/SP, brasileiro, engenheiro, e sua mulher JOANA MARIA EXEMPLO, RG nº "
    "22.222.222-SSP/SP, brasileira,-\npedagoga, casados pelo regime da comunhão de bens, "
    "CEDERAM E TRANS-\nFERIRAM todos os seus direitos e obrigações decorrentes do "
    "compromisso de compra e venda registrado sob nº R.1, à PAULO ROBERTO FICTICIO, RG "
    "33.333.333, brasileiro, solteiro, comerciante."
)


def test_f70_a_cession_of_promise_rights_is_its_own_nature():
    assert "cessao_direitos" in NATUREZAS_ATO
    d = extrair_detalhes_ato(_CESSAO)
    assert d.natureza == "cessao_direitos"
    assert [p.nome for p in d.transmitentes] == ["MARCOS ANTONIO EXEMPLO", "JOANA MARIA EXEMPLO"]
    assert [p.nome for p in d.adquirentes] == ["PAULO ROBERTO FICTICIO"]


def test_f70_a_cession_is_not_a_transfer_of_ownership():
    assert "cessao_direitos" not in NATUREZAS_TRANSFERENCIA


def test_f70_the_cessionario_spouse_follows_f69():
    texto = _CESSAO.replace("solteiro", "casado com a senhora ELISA FICTICIA")
    antes = "PAULO ROBERTO FICTICIO, casado em comunhão universal de bens, com ELISA FICTICIA. "
    nomes = [p.nome for p in extrair_detalhes_ato(texto, anterior=antes).adquirentes]
    assert nomes == ["PAULO ROBERTO FICTICIO", "ELISA FICTICIA"]


@pytest.mark.parametrize("palavra", ["pedagoga", "- pedagoga", "brasileira,- pedagoga", "enfermeira"])
def test_f70_a_profession_after_the_hyphen_form_is_never_a_name(palavra):
    assert not nome_de_parte_valido(palavra)


def test_f70_the_old_cessao_wording_variants():
    for texto in (
        "AV.3 - Cessão de direitos. Os compromissários FULANO EXEMPLO e CICLANO EXEMPLO "
        "cederam os seus direitos sobre o compromisso, a BELTRANO EXEMPLO, brasileiro.",
    ):
        assert extrair_detalhes_ato(texto).natureza == "cessao_direitos"


def test_a_sale_that_merely_mentions_a_prior_cession_stays_a_sale():
    texto = (
        "R. 07/21.748 - Em 10/03/2001. COMPRA E VENDA. FULANO EXEMPLO vendeu o imóvel a "
        "BELTRANO EXEMPLO, brasileiro, imóvel adquirido por cessão de direitos."
    )
    assert extrair_detalhes_ato(texto).natureza == "compra_e_venda"
