"""A card whose registered name is a LABEL, not a person, must not veto a
correctly parsed couple — real, measured (live prod P4, 2026-10-01).

Four of five certidões de casamento read `ok` with estado civil + regime
but ZERO spouses, so no couple was linked and no spouse fact flowed. Run
locally with NO hint, every one of those layouts (the CNJ text-layer block
and the ELE:/ELA: adoption recital) yielded both spouses; with the two
cards' own registered names as hints — `[P4] 858 Vend 1` / `[P4] 858 Vend 2`,
placeholder labels with a bracket and digits — the hint cross-check
(`_leitura_conflita_com_esperados`) saw two printed names compatible with
neither "name" and discarded the whole read. A label cannot rule a real
person out; a hint that cannot be a person's name carries no opinion.

The converse is pinned too: a REAL-looking hint that conflicts still
discards the read (the P2 protection stays), and nothing here ever names a
spouse the document does not print.

Invented names throughout.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.conjuges import find_conjuges
from tests.integrations.documents.test_certidao_casamento_cnj_textlayer import (
    CERTIDAO_CNJ_TEXTLAYER,
)

CERTIDAO_ELE_ELA = (
    "CERTIDAO DE CASAMENTO\n"
    "ELE: RICARDO MOURA SILVA, nascido no dia dez de janeiro de mil "
    "novecentos e oitenta, filho de PEDRO MOURA SILVA e de ANA MOURA SILVA.\n"
    "ELA: PATRICIA ARAUJO PEREIRA, nascida no dia vinte de fevereiro de "
    "mil novecentos e oitenta e dois, filha de JOSE ARAUJO PEREIRA e de "
    "ROSA ARAUJO PEREIRA.\n"
    "Data da celebracao do casamento: 05/06/2010\n"
    "Regime de bens: comunhao parcial de bens\n"
    "Nome que cada um dos conjuges passou a utilizar (quando houver "
    "alteracao): ELE: continuou a usar o mesmo nome. ELA: passou a usar "
    "o nome de PATRICIA ARAUJO SILVA.\n"
)

PLACEHOLDERS = ("[P4] 858 Vend 1", "[P4] 858 Vend 2")
SO_UM = ("[TESTE P4] 858",)


@pytest.mark.parametrize("texto", [CERTIDAO_CNJ_TEXTLAYER, CERTIDAO_ELE_ELA])
@pytest.mark.parametrize("hints", [PLACEHOLDERS, SO_UM, ("[TESTE P4] 871", "[P4] 871 Vend 1")])
def test_placeholder_hints_do_not_discard_a_clean_two_spouse_read(texto, hints):
    sem_hint = find_conjuges(texto)
    assert len(sem_hint) == 2
    com_hint = find_conjuges(texto, esperados=hints)
    assert [c.nome for c in com_hint] == [c.nome for c in sem_hint]


def test_real_looking_conflicting_hints_still_discard_the_read():
    # The P2 protection: a plausible name that matches neither spouse means
    # the read may be garbled -> anchored read only (confirms nothing here).
    assert find_conjuges(
        CERTIDAO_ELE_ELA, esperados=("CARLOS EDUARDO NUNES", "LUCIA HELENA ROCHA")
    ) == ()


def test_a_placeholder_hint_never_confirms_or_names_anyone():
    assert find_conjuges("CERTIDAO sem layout algum", esperados=PLACEHOLDERS) == ()


def test_mixed_hints_keep_only_the_real_name():
    lido = find_conjuges(CERTIDAO_ELE_ELA, esperados=("RICARDO MOURA SILVA", "[P4] 858 Vend 2"))
    assert len(lido) == 2
