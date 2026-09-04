"""`find_cpf` — the holder's CPF off a Brazilian identity document.

🔴 WHAT THESE TESTS ARE REALLY FOR
----------------------------------
The CPF is the one field in this family that can verify itself: two of its
eleven digits are a mod-11 function of the other nine. That changes what a
wrong answer looks like. A parser without the checksum returns a confident,
well-formed, wrong number every time it bites a slice out of a longer digit
run — a CNPJ, a matrícula, a protocol number — and every one of those reads
would be written to a person's record unattended.

So the negative cases below are the point: a CNPJ must not read as a CPF, a
parent's CPF must not be attributed to the holder, and a checksum failure must
degrade rather than pass.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents import find_cpf
from noctusai_lib.integrations.documents.cpf import format_cpf, is_valid, only_digits

#: A real, checksum-valid CPF. Every fixture below derives from it so a change
#: to the validator shows up as one failure rather than twenty.
VALIDO = "412.954.238-98"
VALIDO_NU = "41295423898"

#: Same digits with one transposed — well-formed, eleven digits, invalid.
#: This is what an OCR misread of `VALIDO` actually looks like.
INVALIDO = "412.954.238-99"


class TestChecksum:
    def test_a_real_cpf_verifies(self):
        assert is_valid(VALIDO) is True
        assert is_valid(VALIDO_NU) is True

    def test_a_transposed_digit_fails(self):
        assert is_valid(INVALIDO) is False

    def test_repdigits_are_rejected_even_though_the_arithmetic_passes(self):
        """All ten satisfy mod-11 and all ten are invalid CPFs.

        They are also exactly what placeholder/test data looks like, so
        accepting them would let fixtures through the only gate this module
        has.
        """
        for d in "0123456789":
            assert is_valid(d * 11) is False

    def test_wrong_length_is_not_a_cpf(self):
        assert is_valid("4129542389") is False
        assert is_valid("412954238980") is False


class TestFormatting:
    def test_bare_digits_are_normalised_to_the_canonical_form(self):
        assert format_cpf(VALIDO_NU) == VALIDO

    def test_an_already_formatted_value_survives_unchanged(self):
        assert format_cpf(VALIDO) == VALIDO

    def test_only_digits_strips_punctuation(self):
        assert only_digits(VALIDO) == VALIDO_NU

    def test_a_non_cpf_length_formats_to_none(self):
        assert format_cpf("123") is None


class TestLabelled:
    def test_labelled_and_valid_reads_high(self):
        valor, conf, rotulo = find_cpf(f"NOME FULANO DE TAL\nCPF: {VALIDO}")
        assert (valor, conf) == (VALIDO, "alta")
        assert rotulo == "CPF"

    def test_bare_digits_under_a_label_are_returned_formatted(self):
        """Storage should not depend on how the document punctuated it."""
        valor, conf, _ = find_cpf(f"CPF {VALIDO_NU}")
        assert (valor, conf) == (VALIDO, "alta")

    def test_accents_and_casing_do_not_matter(self):
        valor, conf, _ = find_cpf(f"C.P.F.: {VALIDO}")
        assert (valor, conf) == (VALIDO, "alta")

    def test_labelled_but_checksum_fails_degrades_to_a_suggestion(self):
        """Almost always an OCR digit confusion over a real CPF.

        Worth a human's eyes — never worth writing. The value IS returned, so
        the confirm surface can show what was read.
        """
        valor, conf, _ = find_cpf(f"CPF: {INVALIDO}")
        assert (valor, conf) == (INVALIDO, "baixa")


class TestUnlabelled:
    def test_a_valid_cpf_with_no_label_is_a_low_confidence_suggestion(self):
        """The bare CPF printed under the photo on a modern RG.

        The checksum is the anchor a label would otherwise be — but it is not
        proof the number belongs to the holder rather than to someone else on
        the page, so a human still confirms.
        """
        valor, conf, rotulo = find_cpf(f"REPUBLICA FEDERATIVA DO BRASIL {VALIDO}")
        assert (valor, conf, rotulo) == (VALIDO, "baixa", None)

    def test_an_invalid_unlabelled_number_is_nothing(self):
        """No label and no checksum means no evidence at all."""
        assert find_cpf(f"PROTOCOLO {INVALIDO}") == (None, "nenhuma", None)


class TestDecoys:
    def test_a_cpf_inside_a_filiacao_block_is_demoted_not_trusted(self):
        """🔴 DEMOTED, NOT REJECTED — and the distinction is the whole point.

        `FILIACAO MARIA DE TAL CPF …` is genuinely ambiguous from text alone:
        the block may have ended before the `CPF` label (in which case this is
        the holder's), or the label may belong to the block (a parent's). A
        parser cannot tell without layout.

        Rejecting would drop real holder data on every document that prints a
        filiação block above the CPF — which is most of them. Accepting at
        `alta` would write a parent's CPF onto a person's record unattended.
        So the value survives at `baixa` and lands in the confirm queue, which
        is what that queue is for.

        This exact case was a live defect in `gender.py` before `labels.py`
        was extracted — it returned the parent's sex at `alta`.
        """
        valor, conf, rotulo = find_cpf(f"FILIACAO MARIA DE TAL CPF {VALIDO}")
        assert (valor, conf) == (VALIDO, "baixa")
        assert rotulo == "CPF"

    def test_a_cpf_squarely_inside_a_block_with_no_label_is_rejected(self):
        """No `CPF` label after the block opener — nothing to be ambiguous
        about."""
        assert find_cpf(f"FILIACAO MARIA DE TAL {VALIDO}") == (None, "nenhuma", None)

    def test_a_cnpj_is_not_read_as_a_cpf(self):
        """Fourteen digits. The lookarounds must refuse to bite eleven out.

        Without them the parser returns the first eleven digits of the CNPJ —
        a confident, well-formed, entirely invented CPF.
        """
        valor, conf, _ = find_cpf("CNPJ 12345678000190")
        assert (valor, conf) == (None, "nenhuma")

    def test_a_longer_digit_run_is_not_sliced(self):
        assert find_cpf(f"PROTOCOLO {VALIDO_NU}0000") == (None, "nenhuma", None)

    def test_a_responsavel_block_demotes_the_same_way(self):
        """A minor's document labels the responsável's CPF explicitly."""
        valor, conf, _ = find_cpf(f"RESPONSAVEL CPF {VALIDO}")
        assert (valor, conf) == (VALIDO, "baixa")


class TestDisagreement:
    def test_two_different_labelled_cpfs_report_absence(self):
        """🔴 Never resolved by preferring one.

        Two labelled CPFs means the layout was misread, and picking a winner
        writes a coin-flip onto a person's record.
        """
        outro = "529.982.247-25"
        assert is_valid(outro), "fixture must be a real CPF for this to test anything"
        valor, conf, _ = find_cpf(f"CPF: {VALIDO}\nCPF: {outro}")
        assert (valor, conf) == (None, "nenhuma")

    def test_the_same_cpf_twice_is_agreement_not_disagreement(self):
        valor, conf, _ = find_cpf(f"CPF: {VALIDO}\nCPF {VALIDO_NU}")
        assert (valor, conf) == (VALIDO, "alta")


class TestNothing:
    def test_empty_text(self):
        assert find_cpf("") == (None, "nenhuma", None)

    def test_a_document_that_simply_has_no_cpf(self):
        assert find_cpf("NOME FULANO DE TAL SEXO M") == (None, "nenhuma", None)
