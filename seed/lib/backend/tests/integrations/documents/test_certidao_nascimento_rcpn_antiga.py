"""F102 — the typed old-layout RCPN certidão de nascimento: the birth date is
the one in the "NASCIDO aos ..." clause, never the "lavrado em" registration
date; and the printed filiação ("filho de: X, e de: Y") is read. Synthetic
fixtures mirroring the layout (no real person)."""
from datetime import date

import pytest

from noctusai_lib.integrations.documents.birthdate import (
    data_clausula_nascido,
    find_birthdate,
    normalize,
)
from noctusai_lib.integrations.documents.filiacao import find_filiacao

TODAY = date(2026, 10, 24)

ANTIGA = """CERTIDÃO DE NASCIMENTO
CERTIFICO, que às fls. 185, verso, do livro nº 3-A, sob nº 003936, de REGISTRO DE
NASCIMENTOS, foi lavrado em 03 de março de 1982 o assento do nascimento de:
** FULANO DE TAL TESTE **
NASCIDO, aos dezenove de fevereiro de mil novecentos e oitenta e dois
(((19 de fevereiro de 1982))), às 20:30 horas, em Maternidade Modelo, do sexo
masculino, filho de: BELTRANO DE TAL TESTE, e de: CICLANA DE TAL TESTE, avós
paternos: JOSE TESTE.
OBSERVAÇÃO \\\\ A MARGEM DO TERMO NADA CONSTA ///
Itápolis, 24 de agosto de 2009."""

MODERNA = """CERTIDÃO DE NASCIMENTO
Nome: FULANO DE TAL TESTE
Data de registro: 03/03/1982
Data de nascimento: 19/02/1982
Filiação:
BELTRANO DE TAL TESTE
CICLANA DE TAL TESTE
"""


def test_antiga_birthdate_is_nascido_clause_not_lavrado():
    v, c, label = find_birthdate(ANTIGA, today=TODAY)
    assert (v, c, label) == (date(1982, 2, 19), "alta", "NASCIDO")


def test_lavrado_em_is_a_decoy_without_nascido_clause():
    v, _, _ = find_birthdate("foi lavrado em 03 de março de 1982", today=TODAY)
    assert v is None


def test_antiga_filiacao_read():
    pai, cp, mae, cm, _ = find_filiacao(ANTIGA)
    assert (pai, mae) == ("BELTRANO DE TAL TESTE", "CICLANA DE TAL TESTE")
    assert cp != "nenhuma" and cm != "nenhuma"


def test_moderna_layout_unchanged():
    v, c, _ = find_birthdate(MODERNA, today=TODAY)
    assert (v, c) == (date(1982, 2, 19), "alta")
    pai, _, mae, _, _ = find_filiacao(MODERNA)
    assert (pai, mae) == ("BELTRANO DE TAL TESTE", "CICLANA DE TAL TESTE")


def test_two_nascido_clauses_are_not_attributable():
    t = "nascido em 01/01/1980 ... nascida em 02/02/1985"
    v, _, _ = find_birthdate(t, today=TODAY)
    assert v is None


# ---------------------------------------------------------------------------
# F102 REAL RUN (2026-10-26) — class guard. The fixtures above were written
# from the layout; these mirror the shape the VISION TRANSCRIPTION of the real
# document actually produced (measured over 6 reads, synthetic people only):
# one field per line, the typed form rendered as "LABEL: value", the
# connector after a COLON ("NASCIDO: aos" / "NASCIDO, aos:"), the
# registrar's "////" line-fill, each parent's own "natural de" line between
# the two parents, and a plausible ISSUE date (age ~17 at today) at the foot —
# which makes the bare label race ambiguous, so only the clause can answer.
# ---------------------------------------------------------------------------

TRANSCRITA = """[descrição da imagem] REPÚBLICA FEDERATIVA DO BRASIL:
OFICIAL DE REGISTRO CIVIL DAS PESSOAS NATURAIS:
COMARCA DE CIDADE MODELO - ESTADO DE SÃO PAULO:

TÍTULO: CERTIDÃO DE NASCIMENTO

CERTIFICO: que às fls. 185, verso, do livro nº 3-A, sob nº 003936, de REGISTRO DE NASCIMENTOS, foi lavrado em 03 de março de 1982 o assento do nascimento de:

NOME: FULANO DE TAL TESTE

{conector} dezenove de fevereiro de mil novecentos e oitenta e dois {numerica}às 20:30 horas, em Maternidade Modelo, em Cidade Modelo, Estado de São Paulo, do sexo masculino,

FILHO DE: BELTRANO DE TAL TESTE ////
NATURAL DE: Cidade Modelo (SP)

E DE: CICLANA DE TAL TESTE ////
natural de Outra Cidade (MG)

SENDO AVÓS PATERNOS: Avo Teste ////

OBSERVAÇÃO: \\\\\\ A MARGEM DO TERMO NADA CONSTA ///
O referido é verdade e dou fé.

LOCAL E DATA: Cidade Modelo, 24 de agosto de 2009.
"""


def _transcrita(conector: str, numerica: str = "(((19 de fevereiro de 1982))), ") -> str:
    return TRANSCRITA.format(conector=conector, numerica=numerica)


@pytest.mark.parametrize(
    "conector",
    ["NASCIDO: aos", "NASCIDO, aos:", "NASCIDO, aos", "NASCIDO - aos", "NASCIDO(A): aos"],
)
def test_real_shape_clause_with_any_separator(conector):
    v, c, label = find_birthdate(_transcrita(conector), today=TODAY)
    assert (v, c, label) == (date(1982, 2, 19), "alta", "NASCIDO")


def test_real_shape_birth_date_beyond_the_label_window():
    # The numeric date sits ~100 chars after "NASCIDO" — far past the label
    # race's own window — and the issue date is a second unlabelled plausible
    # candidate: without the clause the read is ambiguous (the prod NULL).
    t = _transcrita("NASCIDO: aos")
    norm = normalize(t)
    assert norm.index("19 DE FEVEREIRO") - norm.index("NASCIDO") > 48
    assert data_clausula_nascido(norm, TODAY) == date(1982, 2, 19)


def test_real_shape_spelled_out_only():
    # A transcription that drops the parenthesized repetition: the spelled
    # date is the only statement of the fact, and it is read.
    v, c, _ = find_birthdate(_transcrita("NASCIDO: aos", numerica=""), today=TODAY)
    assert (v, c) == (date(1982, 2, 19), "alta")


def test_spelled_and_numeric_disagreeing_is_not_a_clause_date():
    t = _transcrita("NASCIDO: aos", numerica="(((19 de fevereiro de 1983))), ")
    assert data_clausula_nascido(normalize(t), TODAY) is None


def test_lavrado_em_alone_never_a_birth_date():
    # Registration date + issue date, no NASCIDO clause at all: the lavrado
    # date is a decoy and must not be reported, at any confidence.
    t = (
        "CERTIDÃO DE NASCIMENTO\nde REGISTRO DE NASCIMENTOS, foi lavrado em: "
        "03 de março de 1982 o assento do nascimento de:\nNOME: FULANO DE TAL TESTE\n"
    )
    v, _, _ = find_birthdate(t, today=TODAY)
    assert v is None
    v, _, _ = find_birthdate(t + "LOCAL E DATA: Cidade Modelo, 24 de agosto de 2009.", today=TODAY)
    assert v != date(1982, 3, 3)


def test_nascido_vivo_without_connector_is_not_a_clause():
    # "DECLARAÇÃO DE NASCIDO VIVO" carries a number/date that is NOT the
    # birth date; the connector (aos/em/no dia) stays required.
    norm = normalize("DECLARACAO DE NASCIDO VIVO: 12/05/1990")
    assert data_clausula_nascido(norm, TODAY) is None


def test_real_shape_filiacao_across_fill_and_parent_naturalidade():
    pai, cp, mae, cm, _ = find_filiacao(_transcrita("NASCIDO: aos"))
    assert (pai, mae) == ("BELTRANO DE TAL TESTE", "CICLANA DE TAL TESTE")
    assert (cp, cm) == ("media", "media")
