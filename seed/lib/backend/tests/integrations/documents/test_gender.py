"""`find_gender` — the holder's sex off a Brazilian identity document.

🔴 WHAT THESE TESTS ARE REALLY FOR
----------------------------------
A sex field has a two-element alphabet, which makes the naive parser ("find M
or F") look correct on every happy-path document and be wrong on real ones. A
single letter appears all over an RG: the issuing state (`SP`), a middle
initial, `DOC. ORIGEM`, the FILIACAO block. So most of what follows are
NEGATIVE tests — the ones that would pass against a parser that should not
ship.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents import find_gender
from noctusai_lib.integrations.documents.gender import FEMININO, MASCULINO


class TestLabelled:
    def test_sexo_m_is_masculino_with_high_confidence(self):
        valor, conf, rotulo = find_gender("NOME FULANO DE TAL\nSEXO: M\nRG 12.345.678")
        assert (valor, conf) == (MASCULINO, "alta")
        assert rotulo == "SEXO"

    def test_sexo_f_is_feminino(self):
        valor, conf, _ = find_gender("SEXO: F")
        assert (valor, conf) == (FEMININO, "alta")

    def test_the_full_word_next_to_the_label_also_reads_high(self):
        valor, conf, _ = find_gender("SEXO MASCULINO")
        assert (valor, conf) == (MASCULINO, "alta")

    def test_accents_and_casing_do_not_matter(self):
        """OCR over a photographed card produces every variant equally."""
        valor, conf, _ = find_gender("Sêxo: Feminino")
        assert (valor, conf) == (FEMININO, "alta")


class TestUnlabelled:
    def test_a_whole_word_alone_is_a_low_confidence_suggestion(self):
        """Unanchored, but `MASCULINO` has no other reason to be on the page."""
        valor, conf, rotulo = find_gender("FULANO DE TAL\nMASCULINO\n12/05/1980")
        assert (valor, conf) == (MASCULINO, "baixa")
        assert rotulo is None

    def test_a_bare_letter_with_no_label_is_never_accepted(self):
        """The whole point of the module.

        `SP` is an issuing state and `F` here is a middle initial. A parser
        that scans for M/F returns a confident wrong answer on this document.
        """
        valor, conf, _ = find_gender("JOAO F PEREIRA\nSSP SP\nRG 12.345.678")
        assert valor is None
        assert conf == "nenhuma"

    def test_a_state_code_does_not_read_as_a_sex(self):
        valor, _, _ = find_gender("ORGAO EMISSOR SSP MG")
        assert valor is None


class TestDecoys:
    def test_a_parents_block_does_not_supply_the_holders_sex(self):
        """Attributing a parent's anything to the holder is the error this
        module family exists to avoid."""
        valor, conf, _ = find_gender("FILIACAO: MARIA F DA SILVA E JOAO M DA SILVA")
        assert valor is None
        assert conf == "nenhuma"

    def test_a_nearer_decoy_beats_a_further_real_label(self):
        """Proximity is what binds a value to a field on these layouts."""
        valor, _, _ = find_gender("SEXO ................ FILIACAO: JOSE M SILVA")
        assert valor is None


class TestDisagreementIsAbsence:
    def test_two_labelled_readings_that_disagree_report_nothing(self):
        """Two different sex values on one document means the layout was
        misread. Picking a winner would write a coin-flip onto a record."""
        valor, conf, _ = find_gender("SEXO: M\nSEXO: F")
        assert valor is None
        assert conf == "nenhuma"

    def test_two_agreeing_labelled_readings_are_still_high(self):
        valor, conf, _ = find_gender("SEXO: M\nSEXO MASCULINO")
        assert (valor, conf) == (MASCULINO, "alta")

    def test_conflicting_unlabelled_words_report_nothing(self):
        valor, conf, _ = find_gender("MASCULINO ... FEMININO")
        assert valor is None
        assert conf == "nenhuma"


class TestNothingThere:
    def test_empty_text(self):
        assert find_gender("") == (None, "nenhuma", None)

    def test_a_document_without_the_field_is_not_an_error(self):
        """A legible document may simply not carry it."""
        valor, conf, _ = find_gender("CPF 123.456.789-00\nNOME FULANO DE TAL")
        assert valor is None
        assert conf == "nenhuma"


class TestNormalisedToWords:
    def test_the_value_is_the_word_the_column_holds_never_a_code(self):
        """The consuming column holds "Masculino" verbatim — returning "M"
        would mean every reader decoding it, and the first one that forgot
        would store a letter where the product expects a word."""
        valor, _, _ = find_gender("SEXO: M")
        assert valor == "Masculino"
