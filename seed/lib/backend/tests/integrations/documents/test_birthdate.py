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


class TestCnhCombinedBirthdateLabel:
    """P1/883 (2026-09-24): the CNH prints birth date, city and UF as ONE
    field, "DATA, LOCAL E UF DE NASCIMENTO" — an explicit entry now, not
    only the bare `NASCIMENTO` substring match."""

    def test_the_full_cnh_label(self):
        v, c, label = find_birthdate(
            "DATA, LOCAL E UF DE NASCIMENTO: 16/02/1990, SAO PAULO, SP", today=TODAY
        )
        assert (v, c) == (date(1990, 2, 16), "alta")
        assert label == "DATA, LOCAL E UF DE NASCIMENTO"

    def test_the_shorter_cnh_variant(self):
        v, c, _ = find_birthdate(
            "DATA E LOCAL DE NASCIMENTO: 16/02/1990 SAO PAULO SP", today=TODAY
        )
        assert (v, c) == (date(1990, 2, 16), "alta")

    def test_survives_a_neighbouring_habilitacao_decoy(self):
        """The CNH's own layout: expedição/validade/primeira habilitação
        sit in one row, the combined nascimento field in another."""
        texto = (
            "DATA EXPEDICAO / VALIDADE / 1A HABILITACAO: "
            "10/01/2020 10/01/2030 20/05/2008 "
            "DATA, LOCAL E UF DE NASCIMENTO: 16/02/1990, SAO PAULO, SP"
        )
        v, c, label = find_birthdate(texto, today=TODAY)
        assert (v, c) == (date(1990, 2, 16), "alta")
        assert label == "DATA, LOCAL E UF DE NASCIMENTO"


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


class TestColumnarDateFormat:
    """🔴 THE BUG THIS CLASS CLOSES — real, measured (P1/883, 2026-09-28)

    A tabular certidão layout prints every date as three separate table
    COLUMNS ("DIA MES ANO" headers over bare numbers), with only
    whitespace between day/month/year — no `/`, `.` or `-` for
    `_NUMERIC_DATE` to anchor on. The birthdate was not misread on this
    layout, it was simply never a CANDIDATE at all.
    """

    def test_a_columnar_date_under_its_own_header_is_read(self):
        texto = "DATA DE NASCIMENTO\nDIA MES ANO\n04 10 1961"
        v, c, label = find_birthdate(texto, today=TODAY)
        assert (v, c) == (date(1961, 10, 4), "alta")
        assert label == "DATA DE NASCIMENTO"

    def test_a_columnar_decoy_is_rejected_same_as_a_slashed_one(self):
        """The new date FORM must not bypass the existing label/decoy
        machinery — a columnar date under a REGISTRO field is still not a
        birthdate."""
        v, c, _ = find_birthdate("DATA DE REGISTRO\nDIA MES ANO\n04 10 1961", today=TODAY)
        assert (v, c) == (None, "nenhuma")

    def test_a_registry_matricula_number_is_not_misread_as_a_date(self):
        """🔴 THE FALSE-POSITIVE THIS GUARDS AGAINST — a CNJ-format
        matrícula (`AAAAAA CC UU YYYY T NNNNN LLL NNNNNNN-DV`) has its OWN
        3rd/4th/5th space-separated groups shaped exactly like a calendar
        day/month/year, and its "year" is a real registration year — not
        anyone's age. Embedded inside the longer digit-group chain, it
        must not be read as a columnar date."""
        matricula = "223344 05 10 1998 3 00276 144 0012345-67"
        assert find_birthdate(matricula, today=TODAY) == (None, "nenhuma", None)

    def test_a_standalone_columnar_triple_with_no_label_is_low_confidence(self):
        """Same posture every other date form in this module already
        takes: genuinely unlabelled is a guess, typed as one — never
        promoted by the new form alone."""
        v, c, label = find_birthdate("Documento emitido\n04 10 1961", today=TODAY)
        assert (v, c, label) == (date(1961, 10, 4), "baixa", None)


class TestScatteredDiaMesAnoFormat:
    """🔴 THE BUG THIS CLASS CLOSES — real, measured (P2 corpus, 2026-09-30)

    A CNJ text-layer certidão de casamento prints EACH sub-label and its
    value on its own line — "Dia" / "99" / "Mês" / "99" / "Ano" / "9999" —
    one fragmentation step further than `TestColumnarDateFormat`'s "DIA MES
    ANO" header over three bare numbers. `_COLUMNAR_DATE` requires the three
    numbers directly adjacent (only whitespace between them); interspersing
    the sub-labels between each number made the birthdate invisible on
    every spouse's own block."""

    def test_dia_mes_ano_each_on_their_own_line_under_nascimento(self):
        texto = (
            "Data de nascimento\n"
            "Dia\n04\nMês\n10\nAno\n1961\n"
        )
        v, c, label = find_birthdate(texto, today=TODAY)
        assert (v, c) == (date(1961, 10, 4), "alta")
        assert label == "DATA DE NASCIMENTO"

    def test_the_marriage_celebration_date_on_the_same_scaffold_is_rejected(self):
        texto = "Data da celebração do casamento\nDia\n04\nMês\n10\nAno\n2020\n"
        assert find_birthdate(texto, today=TODAY) == (None, "nenhuma", None)

    def test_the_registration_date_on_the_same_scaffold_is_rejected(self):
        texto = "Data de registro\nDia\n04\nMês\n10\nAno\n2020\n"
        assert find_birthdate(texto, today=TODAY) == (None, "nenhuma", None)

    def test_a_spouses_birthdate_survives_alongside_the_marriage_date_in_the_same_text(self):
        """The exact real shape: one certidão states BOTH — the marriage's
        own celebration date and a nubente's birthdate — each on the
        identical Dia/Mês/Ano scaffold. Only the labelled-birthdate one is
        read; the celebration date is excluded by its own decoy label, never
        by disagreeing with the birthdate."""
        texto = (
            "Data da celebração do casamento\nDia\n15\nMês\n06\nAno\n2020\n"
            "Nome do conjuge Joana Exemplo\n"
            "Data de nascimento\nDia\n04\nMês\n10\nAno\n1961\n"
        )
        v, c, label = find_birthdate(texto, today=TODAY)
        assert (v, c) == (date(1961, 10, 4), "alta")
        assert label == "DATA DE NASCIMENTO"

    def test_an_unlabelled_scattered_triple_is_never_promoted_alone(self):
        """No birth label anywhere near it: same posture as every other
        unlabelled form — reported absent outright, since the bare
        `DIA`/`MES`/`ANO` tokens are not themselves a decoy OR a birth
        label, so this shape without a nearby real label sits with the
        columnar family's own convention of never guessing from shape
        alone once a real label vocabulary exists for it."""
        texto = "Documento\nDia\n04\nMês\n10\nAno\n1961\n"
        v, c, label = find_birthdate(texto, today=TODAY)
        assert (v, c, label) == (date(1961, 10, 4), "baixa", None)
