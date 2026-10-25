"""F102 — the typed old-layout RCPN certidão de nascimento: the birth date is
the one in the "NASCIDO aos ..." clause, never the "lavrado em" registration
date; and the printed filiação ("filho de: X, e de: Y") is read. Synthetic
fixtures mirroring the layout (no real person)."""
from datetime import date

from noctusai_lib.integrations.documents.birthdate import find_birthdate
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
