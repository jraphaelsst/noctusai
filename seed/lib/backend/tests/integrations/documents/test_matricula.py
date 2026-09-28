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

    def test_abbreviated_protocolo_does_not_masquerade_as_a_second_matricula(self):
        """P1/883 live bug (2026-09-24): "Mat. 3917 - Página 1/3 - Prot.
        123456" is the exact running-header shape a real scanned matrícula
        printed. "Prot." (the abbreviation) is not the string "PROTOCOLO",
        so the protocol number fell through to the nearest REAL label
        ("MAT.") in its 40-char window and read as a second, disagreeing
        matrícula number — zeroing the whole result via
        `TestDisagreementIsAbsence`'s rule, for a document that in fact
        named its matrícula cleanly, once."""
        texto = "Mat. 3917 - Página 1/3 - Prot. 123456"
        valor, conf, rotulo = find_matricula(texto)
        assert (valor, conf) == ("3917", "alta")
        assert rotulo and "MAT" in rotulo

    def test_the_full_protocolo_word_is_still_a_decoy_too(self):
        valor, _, _ = find_matricula("MATRICULA 12.345 PROTOCOLO 987654")
        assert valor == "12345"


class TestWhichMatricula:
    def test_a_matricula_cited_in_the_body_does_not_win(self):
        """🔴 The error nobody catches until a cartório rejects the paperwork:
        attaching a neighbour's registry number to this sale."""
        texto = "MATRICULA Nº 555 LIVRO 2 ORIGINADA DA MATRICULA 12.345"
        valor, conf, _ = find_matricula(texto)
        assert (valor, conf) == ("555", "alta")

    def test_a_body_only_match_is_offered_as_a_suggestion(self):
        """The heading did not survive transcription. Plausible, not writable
        unattended — but only when the body match ISN'T itself a citation of
        another property (see `TestCitationsAreExcludedNotOffered` below:
        "ORIGINADA DA MATRICULA X" is exactly that citation shape, so it no
        longer lands here)."""
        valor, conf, _ = find_matricula("AVERBACAO CONSTA MATRICULA 12.345")
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


class TestCitationsAreExcludedNotOffered:
    """P2 corpus, 2026-09: once the heading fails, the old body-fallback took
    `corpo[0]` unconditionally — and on every failing real document that was a
    citation of the PARENT property. A blank beats a neighbour's number."""

    def test_registro_anterior_citation_is_excluded(self):
        texto = "REGISTRO ANTERIOR: 99 DA MATRICULA NO 9.999, FEITO EM 2020"
        valor, conf, _ = find_matricula(texto)
        assert (valor, conf) == (None, "nenhuma")

    def test_r_barra_m_prefix_is_excluded_even_with_the_marker_word_too(self):
        texto = "REGISTRO ANTERIOR: R.99/M-999.999, DE 01/01/2020 DESTE REGISTRO"
        valor, conf, _ = find_matricula(texto)
        assert (valor, conf) == (None, "nenhuma")

    def test_bare_m_prefix_right_before_the_number_is_excluded(self):
        """"M-" directly in front of a number is the citation shorthand on its
        own, regardless of how far back a marker WORD sits."""
        texto = "(OU 8888-77 MATRICULA MAIOR). REGISTRO ANTERIOR: R.9/M-99.999"
        valor, conf, _ = find_matricula(texto)
        assert (valor, conf) == (None, "nenhuma")


class TestCNMOutranksTheHeading:
    """The Código Nacional de Matrícula (Provimento CNJ 143/2023) carries its
    own ISO 7064 MOD 97-10 check digits — the only number on the page that is
    self-verifying. DVs below are the real computation, not made up."""

    def test_a_dv_invalid_cnm_is_ignored(self):
        """300000.2.0011111 would check as -27; -28 is deliberately wrong."""
        texto = (
            "CNM - CODIGO NACIONAL DE MATRICULA (300000.2.0011111-28) "
            "LIVRO N.O 2 - REGISTRO GERAL SERVENTIA DO REGISTRO DE IMOVEIS "
            "DE TESTE"
        )
        valor, conf, _ = find_matricula(texto)
        assert (valor, conf) == (None, "nenhuma")

    def test_two_disagreeing_valid_cnms_are_ignored(self):
        """Both check out on their own DV, but they name different
        matrículas — disagreement is absence here too, same rule as two
        disagreeing heading labels."""
        texto = "CNM 400000.2.0022222-17 E TAMBEM CNM 400000.2.0033333-52 REGISTRO GERAL"
        valor, conf, _ = find_matricula(texto)
        assert (valor, conf) == (None, "nenhuma")

    def test_cnm_rescues_an_unlabelled_heading(self):
        """Failure mode 3: no real label survives transcription (only decoys
        sit within the 40-char window), so the heading yields nothing — but
        the CNM alongside it is untouched."""
        texto = (
            "CNM - CODIGO NACIONAL DE MATRICULA (200000.2.0067890-67) "
            "LIVRO N.O 2 - REGISTRO GERAL SERVENTIA DO REGISTRO DE IMOVEIS "
            "DE TESTE - CNJ NO1234-5 6789 -54.321- 01 TESTE"
        )
        valor, conf, rotulo = find_matricula(texto)
        assert (valor, conf) == ("67890", "alta")
        assert rotulo == "CNM"

    def test_cnm_confirms_an_agreeing_heading(self):
        texto = "CNM 100000.2.0054321-79 MATRICULA 54.321 FICHA 01 VERSO"
        valor, conf, _ = find_matricula(texto)
        assert (valor, conf) == ("54321", "alta")

    def test_cnm_wins_over_a_disagreeing_heading(self):
        """The corpus's heading 'disagreements' turned out to be label-row
        misreads, not real ambiguity — so a DV-valid CNM overrides them."""
        texto = "MATRICULA 111 MATRICULA Nº 222 CNM 500000.2.0099999-23"
        valor, conf, rotulo = find_matricula(texto)
        assert (valor, conf) == ("99999", "alta")
        assert rotulo == "CNM"


class TestStackedHeaderLayout:
    """Failure mode 1: the labels print "MATRICULA ... FICHA" on one row, the
    values on the next, so `_label_before`'s proximity rule only ever sees
    FICHA — the nearer decoy — and the heading yields nothing."""

    def test_labels_then_two_numbers_on_the_next_line(self):
        texto = (
            "LIVRO NO 2 REGISTRO GERAL MATRICULA FICHA 12.345 01 "
            "REGISTRO DE IMOVEIS DE TESTE"
        )
        valor, conf, rotulo = find_matricula(texto)
        assert (valor, conf) == ("12345", "alta")
        assert rotulo == "MATRICULA FICHA"

    def test_pipe_delimited_table_layout(self):
        texto = (
            "SERVENTIA DO REGISTRO DE IMOVEIS DE TESTE | MATRICULA | FICHA | "
            "| -54.321- | 02 | TESTE, DE JANEIRO DE 2026"
        )
        valor, conf, rotulo = find_matricula(texto)
        assert (valor, conf) == ("54321", "alta")
        assert rotulo == "MATRICULA FICHA"
