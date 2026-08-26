"""`find_matricula` — this document's OWN registry number.

🔴 WHAT THESE ARE FOR
---------------------
A matrícula is wall-to-wall numbers: livro, folha, CNM, IPTU inscription, CEP,
CPF, protocol, área — most of them 4–8 digits and shaped exactly like the
answer. "Longest number" and "first number" both return something plausible on
every document, which is why almost everything below is a NEGATIVE test.

The second family is about WHICH matrícula. The body of a matrícula cites other
matrículas constantly ("originada da matrícula 12.345"), and those are real
labelled matches for a different property.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents import find_matricula


class TestLabelledInTheHeading:
    def test_the_plain_case(self):
        valor, conf, rotulo = find_matricula("MATRICULA Nº 12.345\nLIVRO 2")
        assert (valor, conf) == ("12345", "alta")
        assert rotulo and "MATRICULA" in rotulo

    def test_thousands_dots_are_dropped(self):
        """`12.345` and `12345` are the same matrícula; storing both spellings
        would make the column fail to match itself."""
        assert find_matricula("MATRICULA 12.345")[0] == "12345"
        assert find_matricula("MATRICULA 12345")[0] == "12345"

    def test_a_short_comarca_number_is_accepted(self):
        """Numbering is per-cartório — three digits is real."""
        assert find_matricula("MATRICULA Nº 742")[0] == "742"

    def test_a_long_sao_paulo_number_is_accepted(self):
        assert find_matricula("MATRICULA 123456789")[0] == "123456789"

    def test_accents_and_casing_do_not_matter(self):
        assert find_matricula("Matrícula nº 12.345")[0] == "12345"


class TestTheDecoysOnTheSamePage:
    def test_livro_is_not_the_matricula(self):
        """Printed inches away, same typeface, same line."""
        valor, _, _ = find_matricula("LIVRO 2 FOLHA 145")
        assert valor is None

    def test_folha_next_to_matricula_does_not_win(self):
        valor, _, _ = find_matricula("MATRICULA 12.345 LIVRO 2 FOLHA 145")
        assert valor == "12345"

    def test_iptu_inscription_is_not_the_matricula(self):
        valor, _, _ = find_matricula("INSCRICAO IPTU 087.654.321")
        assert valor is None

    def test_cpf_is_not_the_matricula(self):
        valor, _, _ = find_matricula("CPF 123.456.789-00")
        assert valor is None

    def test_an_unlabelled_number_is_never_taken(self):
        """🔴 No low-confidence fallback here, unlike the birthdate: a
        well-formed date is itself evidence, an unlabelled integer on a
        matrícula is evidence of nothing."""
        valor, conf, _ = find_matricula("CARTORIO DE REGISTRO 12345 SAO PAULO")
        assert valor is None
        assert conf == "nenhuma"


class TestWhichMatricula:
    def test_a_matricula_cited_in_the_body_does_not_win(self):
        """🔴 The error nobody catches until a cartório rejects the paperwork:
        attaching a neighbour's registry number to this sale."""
        texto = "MATRICULA Nº 555 LIVRO 2 ORIGINADA DA MATRICULA 12.345"
        valor, conf, _ = find_matricula(texto)
        assert (valor, conf) == ("555", "alta")

    def test_a_body_only_match_is_offered_as_a_suggestion(self):
        """The heading did not survive transcription. Plausible, not writable
        unattended."""
        valor, conf, _ = find_matricula("ORIGINADA DA MATRICULA 12.345")
        assert (valor, conf) == ("12345", "baixa")

    def test_averbacao_marks_the_body_too(self):
        texto = "MATRICULA 777 AV.1 MATRICULA 888"
        assert find_matricula(texto)[0] == "777"


class TestDisagreementIsAbsence:
    def test_two_conflicting_heading_numbers_report_nothing(self):
        """Choosing one would attach a registry number to a property at
        random."""
        valor, conf, _ = find_matricula("MATRICULA 111 MATRICULA Nº 222")
        assert valor is None
        assert conf == "nenhuma"

    def test_two_agreeing_heading_numbers_are_still_high(self):
        valor, conf, _ = find_matricula("MATRICULA 12.345 ... MATRICULA Nº 12345")
        assert (valor, conf) == ("12345", "alta")


class TestNothingThere:
    def test_empty(self):
        assert find_matricula("") == (None, "nenhuma", None)

    def test_a_document_without_the_field(self):
        valor, conf, _ = find_matricula("CERTIDAO NEGATIVA DE DEBITOS")
        assert valor is None
        assert conf == "nenhuma"
