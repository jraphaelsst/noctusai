"""The extraction rules that decide whether a wrong birthday gets stored.

Every test here is a failure mode observed on real Brazilian identity
layouts, not a synthetic edge case. The decoy tests in particular are the
whole reason the module is label-anchored: on a standard RG the expedição
date is printed ABOVE the birthdate, so a positional extractor is wrong
more often than right — and wrong in the worst way, producing a real date.
"""
from datetime import date

import pytest

from noctusai_lib.integrations.documents.birthdate import find_birthdate, normalize

TODAY = date(2026, 8, 22)


class TestLabelAnchored:
    def test_plain_label(self):
        v, c, label = find_birthdate("Data de Nascimento: 12/05/1980", today=TODAY)
        assert v == date(1980, 5, 12)
        assert c == "alta"
        assert label == "DATA DE NASCIMENTO"

    def test_label_split_across_a_line_break(self):
        """OCR routinely breaks a label from its value; the proximity
        window must span that."""
        v, c, _ = find_birthdate("DATA DE NASCIMENTO\n12/05/1980", today=TODAY)
        assert (v, c) == (date(1980, 5, 12), "alta")

    def test_accents_and_case_are_irrelevant(self):
        v, c, _ = find_birthdate("data de nascimento 12/05/1980", today=TODAY)
        assert (v, c) == (date(1980, 5, 12), "alta")

    def test_abbreviated_label(self):
        v, c, _ = find_birthdate("DT NASC 03/11/1975", today=TODAY)
        assert (v, c) == (date(1975, 11, 3), "alta")

    def test_dotted_and_dashed_separators(self):
        for text in ("Nascimento: 12.05.1980", "Nascimento: 12-05-1980"):
            v, c, _ = find_birthdate(text, today=TODAY)
            assert (v, c) == (date(1980, 5, 12), "alta"), text

    def test_textual_month(self):
        v, c, _ = find_birthdate("Nascido em 12 de maio de 1980", today=TODAY)
        assert (v, c) == (date(1980, 5, 12), "alta")

    def test_vision_narrative_shape_is_parsed(self):
        """The rasterize→vision rung emits the product's structured
        prose, not raw document text. Same parser must read both."""
        narrative = (
            "Tipo: RG\n"
            "Resumo: Documento de identidade brasileiro.\n"
            "Dados visíveis:\n"
            "- nome: MARIA SILVA\n"
            "- data de nascimento: 12/05/1980\n"
            "- órgão emissor: SSP/SP\n"
        )
        v, c, _ = find_birthdate(narrative, today=TODAY)
        assert (v, c) == (date(1980, 5, 12), "alta")


class TestDecoyDatesAreRejected:
    """🔴 The core defect this module exists to prevent."""

    def test_expedicao_above_nascimento_picks_nascimento(self):
        rg = "DATA DE EXPEDICAO 10/03/1995 DATA DE NASCIMENTO 12/05/1980"
        v, c, label = find_birthdate(rg, today=TODAY)
        assert v == date(1980, 5, 12), "took the expedição date — the classic RG misread"
        assert label == "DATA DE NASCIMENTO"
        assert c == "alta"

    def test_a_lone_validade_is_not_a_birthdate(self):
        v, c, _ = find_birthdate("VALIDADE 01/02/1999", today=TODAY)
        assert (v, c) == (None, "nenhuma")

    def test_cnh_primeira_habilitacao_is_not_a_birthdate(self):
        v, _, _ = find_birthdate(
            "DATA DA PRIMEIRA HABILITACAO 04/09/2001 NASCIMENTO 12/05/1980",
            today=TODAY,
        )
        assert v == date(1980, 5, 12)

    def test_nearest_label_wins_not_the_first_one(self):
        v, _, label = find_birthdate(
            "NASCIMENTO 12/05/1980 EMISSAO 07/07/2010", today=TODAY
        )
        assert v == date(1980, 5, 12)
        assert label == "NASCIMENTO"


class TestSanityGate:
    def test_future_date_rejected(self):
        assert find_birthdate("Nascimento: 12/05/2030", today=TODAY)[0] is None

    def test_implausibly_old_rejected(self):
        """A digit confusion (1980 → 1830), not a supercentenarian."""
        assert find_birthdate("Nascimento: 12/05/1830", today=TODAY)[0] is None

    def test_implausibly_young_rejected(self):
        assert find_birthdate("Nascimento: 12/05/2020", today=TODAY)[0] is None

    def test_boundary_ages_accepted(self):
        assert find_birthdate("Nascimento: 22/08/2010", today=TODAY)[0] == date(2010, 8, 22)
        assert find_birthdate("Nascimento: 22/08/1906", today=TODAY)[0] == date(1906, 8, 22)

    def test_impossible_calendar_date_is_skipped_not_raised(self):
        assert find_birthdate("Nascimento: 32/13/1980", today=TODAY)[0] is None


class TestAmbiguityIsReportedNotResolved:
    def test_two_disagreeing_labelled_dates_degrade_to_nothing(self):
        v, c, _ = find_birthdate(
            "NASCIMENTO 12/05/1980 DATA DE NASCIMENTO 03/11/1975", today=TODAY
        )
        assert (v, c) == (None, "nenhuma"), "picked a winner between contradictory reads"

    def test_two_agreeing_labelled_dates_stay_high_confidence(self):
        v, c, _ = find_birthdate(
            "NASCIMENTO 12/05/1980 DATA DE NASCIMENTO 12/05/1980", today=TODAY
        )
        assert (v, c) == (date(1980, 5, 12), "alta")

    def test_single_unlabelled_plausible_date_is_low_confidence(self):
        v, c, label = find_birthdate("Documento emitido 12/05/1980", today=TODAY)
        assert (v, c, label) == (date(1980, 5, 12), "baixa", None)

    def test_several_unlabelled_dates_yield_nothing(self):
        v, c, _ = find_birthdate("12/05/1980 e 03/11/1975", today=TODAY)
        assert (v, c) == (None, "nenhuma")


class TestNoFalsePositives:
    def test_cpf_number_is_not_read_as_a_date(self):
        v, _, _ = find_birthdate("CPF 123.456.789-01", today=TODAY)
        assert v is None

    def test_two_digit_year_is_not_guessed(self):
        """`12/05/80` is genuinely ambiguous; a pivot-year convention
        would manufacture confidence."""
        assert find_birthdate("Nascimento: 12/05/80", today=TODAY)[0] is None

    def test_empty_and_none_safe(self):
        assert find_birthdate("", today=TODAY) == (None, "nenhuma", None)
        assert find_birthdate(None, today=TODAY) == (None, "nenhuma", None)


def test_normalize_strips_accents_and_collapses_whitespace():
    assert normalize("  Data  de\n Nascimento é  ") == "DATA DE NASCIMENTO E"
