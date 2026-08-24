"""The name parser, and specifically the ways it must REFUSE to answer.

A wrong birthdate is caught by a plausibility gate. A wrong name is not
catchable by anything: `MARIA APARECIDA DOS SANTOS` read off the FILIAÇÃO
line instead of the NOME line is a real, well-formed Brazilian name that
no downstream check can distinguish from the right answer. So most of
this file is about the parser declining.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.name import find_name, looks_like_a_name
from noctusai_lib.integrations.documents.text import normalize_lines, strip_accents_upper


# ─── Realistic layouts ───────────────────────────────────────────────────

RG_LAYOUT = """
REPUBLICA FEDERATIVA DO BRASIL
SECRETARIA DE SEGURANCA PUBLICA
CARTEIRA DE IDENTIDADE
REGISTRO GERAL
12.345.678-9
NOME
JOAO PEREIRA DA SILVA
FILIACAO
ANTONIO PEREIRA DA SILVA
MARIA APARECIDA DOS SANTOS
DATA DE NASCIMENTO
12/05/1980
NATURALIDADE
SAO PAULO SP
"""

CPF_LAYOUT = """
MINISTERIO DA FAZENDA
SECRETARIA DA RECEITA FEDERAL
CADASTRO DE PESSOAS FISICAS
NOME
ANA CAROLINA DE OLIVEIRA
NUMERO DE INSCRICAO
123.456.789-00
NASCIMENTO
03/11/1975
"""

INLINE_LAYOUT = """
NOME: CARLOS EDUARDO MENDES
DATA DE NASCIMENTO: 22/07/1990
"""


class TestHappyPaths:
    def test_name_on_the_line_after_the_label(self):
        value, confidence, label = find_name(RG_LAYOUT)
        assert value == "JOAO PEREIRA DA SILVA"
        assert confidence == "alta"
        assert label == "NOME"

    def test_name_on_the_same_line_as_the_label(self):
        value, confidence, _ = find_name(INLINE_LAYOUT)
        assert value == "CARLOS EDUARDO MENDES"
        assert confidence == "alta"

    def test_cpf_layout(self):
        value, confidence, _ = find_name(CPF_LAYOUT)
        assert value == "ANA CAROLINA DE OLIVEIRA"
        assert confidence == "alta"

    def test_accents_are_folded(self):
        value, _, _ = find_name("NOME\nJOÃO CONCEIÇÃO MÜLLER\n")
        assert value == "JOAO CONCEICAO MULLER"


class TestFiliacaoIsNeverRead:
    """The single most dangerous decoy on a Brazilian RG."""

    def test_parents_under_filiacao_are_not_the_holder(self):
        value, _, _ = find_name(RG_LAYOUT)
        assert value == "JOAO PEREIRA DA SILVA"
        assert "ANTONIO" not in (value or "")
        assert "MARIA" not in (value or "")

    def test_a_document_with_only_filiacao_yields_nothing(self):
        """No NOME label at all — the parents must not fill the vacancy."""
        text = "FILIACAO\nANTONIO PEREIRA DA SILVA\nMARIA APARECIDA DOS SANTOS\n"
        assert find_name(text) == (None, "nenhuma", None)

    @pytest.mark.parametrize(
        "label", ["NOME DO PAI", "NOME DA MAE", "NOME DO CONJUGE"]
    )
    def test_explicit_relative_labels_are_decoys(self, label):
        """`NOME DO PAI` must match as itself, not as `NOME` + a value."""
        assert find_name(f"{label}: ANTONIO PEREIRA DA SILVA\n") == (
            None, "nenhuma", None,
        )

    def test_holder_is_still_found_when_a_relative_label_is_present(self):
        text = "NOME: JOAO PEREIRA DA SILVA\nNOME DA MAE: MARIA DOS SANTOS\n"
        value, confidence, _ = find_name(text)
        assert value == "JOAO PEREIRA DA SILVA"
        assert confidence == "alta"


class TestInstitutionalPhrasesAreNotNames:
    @pytest.mark.parametrize(
        "phrase",
        [
            "REPUBLICA FEDERATIVA DO BRASIL",
            "SECRETARIA DE SEGURANCA PUBLICA",
            "CADASTRO DE PESSOAS FISICAS",
            "CARTEIRA DE IDENTIDADE",
            "VALIDA EM TODO O TERRITORIO NACIONAL",
        ],
    )
    def test_blocklisted_phrase_rejected(self, phrase):
        assert looks_like_a_name(phrase) is False

    def test_a_label_followed_by_an_institutional_line_finds_nothing(self):
        assert find_name("NOME\nSECRETARIA DE SEGURANCA PUBLICA\n") == (
            None, "nenhuma", None,
        )


class TestStructuralRejects:
    @pytest.mark.parametrize(
        "candidate",
        [
            "",
            "JO",                      # too short
            "JOAO",                    # one word only
            "JOAO 123",                # digits
            "123.456.789-00",          # a CPF number
            "J S",                     # initials only
            "DE DA DO",                # particles only
            "A" * 90,                  # absurdly long
        ],
    )
    def test_rejected(self, candidate):
        assert looks_like_a_name(candidate) is False

    @pytest.mark.parametrize(
        "candidate",
        [
            "JOAO SILVA",
            "ANA CAROLINA DE OLIVEIRA",
            "MARIA DA CONCEICAO E SOUZA",
            "JEAN-PIERRE MARTINS",
            "MARIA D'AVILA COSTA",
        ],
    )
    def test_accepted(self, candidate):
        assert looks_like_a_name(candidate) is True


class TestAmbiguityIsReportedNotResolved:
    def test_two_different_labelled_names_yield_nothing(self):
        """Two NOME labels disagreeing means the layout was misread."""
        text = "NOME: JOAO PEREIRA DA SILVA\nNOME: CARLOS EDUARDO MENDES\n"
        assert find_name(text) == (None, "nenhuma", None)

    def test_the_same_name_twice_is_not_ambiguous(self):
        text = "NOME: JOAO PEREIRA DA SILVA\nNOME: JOAO PEREIRA DA SILVA\n"
        value, confidence, _ = find_name(text)
        assert value == "JOAO PEREIRA DA SILVA"
        assert confidence == "alta"


class TestNoUnlabelledFallback:
    def test_a_name_shaped_line_without_a_label_is_not_read(self):
        """Deliberately unlike `find_birthdate`, which has a `baixa` fallback.

        The equivalent guess here is "the longest name-shaped line", which
        on an RG is frequently a parent.
        """
        assert find_name("JOAO PEREIRA DA SILVA\n12/05/1980\n") == (
            None, "nenhuma", None,
        )

    def test_baixa_is_never_returned_by_the_parser(self):
        """Source-based tempering is the adapter's job, not this module's."""
        for text in (RG_LAYOUT, CPF_LAYOUT, INLINE_LAYOUT, "", "NOME\n"):
            assert find_name(text)[1] in {"alta", "nenhuma"}


class TestLabelBoundaries:
    def test_a_word_starting_with_nome_is_not_the_label(self):
        assert find_name("NOMEACAO DE CARGO\nJOAO PEREIRA DA SILVA\n") == (
            None, "nenhuma", None,
        )

    def test_a_label_whose_value_fails_validation_does_not_reach_further(self):
        """`NOME: 123` must not fall through and claim the next line."""
        assert find_name("NOME: 123456\nJOAO PEREIRA DA SILVA\n") == (
            None, "nenhuma", None,
        )


class TestTextNormalisation:
    def test_lines_survive(self):
        assert normalize_lines("a\n\n  b  \nc") == ["A", "B", "C"]

    def test_accents_stripped_and_uppercased(self):
        assert strip_accents_upper("José Ção") == "JOSE CAO"

    def test_empty_input(self):
        assert normalize_lines("") == []
        assert find_name("") == (None, "nenhuma", None)


class TestPredicateIsSafeForRawInput:
    """`looks_like_a_name` is used outside the parser, on un-normalised text.

    The checklist derivation asks it "is this registration value actually a
    full name?" — and registration values are mixed-case and accented.
    """

    @pytest.mark.parametrize(
        "raw",
        ["Ana Carolina de Oliveira", "joão pereira da silva", "JOSÉ DA SILVA"],
    )
    def test_mixed_case_and_accented_full_names_accepted(self, raw):
        assert looks_like_a_name(raw) is True

    @pytest.mark.parametrize(
        "raw",
        ["Ana", "ana", "  Ana  ", "Ana 2", "Cliente 123", "Maria (corretora)"],
    )
    def test_push_names_and_junk_still_rejected(self, raw):
        assert looks_like_a_name(raw) is False

    def test_normalisation_is_idempotent(self):
        once = strip_accents_upper("José da Silva")
        assert looks_like_a_name(once) is looks_like_a_name("José da Silva")
