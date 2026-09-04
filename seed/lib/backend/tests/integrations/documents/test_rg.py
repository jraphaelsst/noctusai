"""`find_rg` / `find_rg_orgao` — the RG number and its issuer.

🔴 WHAT THESE TESTS ARE REALLY FOR
----------------------------------
The RG is the weakest field in this family and the tests exist to keep it
honest. There is no national format and no check digit anywhere in Brazil, so
`52179965` carries zero self-evidence: it is equally consistent with an RG, a
matrícula, a protocol number, or half a phone number. The parser therefore
demands a label — the same discipline `gender.py` applies to a bare `M` — with
one exception earned by punctuation.

The two failure modes worth guarding, both of which produce a *plausible* wrong
answer rather than an obvious one:

1. Reading the CPF printed one line below an `RG` label as the RG.
2. Reading a property's matrícula as a person's RG, because this same extractor
   runs over documents uploaded to an imóvel's file.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents import find_rg, find_rg_orgao
from noctusai_lib.integrations.documents.rg import only_alnum

#: São Paulo's shape: dotted thousands plus an alphanumeric check character.
SP = "52.179.965-X"
SP_NU = "52179965X"

#: A real, checksum-valid CPF — the decoy that matters most.
CPF = "412.954.238-98"


class TestLabelled:
    def test_labelled_reads_high_and_keeps_the_printed_form(self):
        valor, conf, rotulo = find_rg(f"NOME FULANO DE TAL\nRG {SP}")
        assert (valor, conf) == (SP, "alta")
        assert rotulo == "RG"

    def test_bare_digits_under_a_label_are_accepted(self):
        valor, conf, _ = find_rg(f"REGISTRO GERAL {SP_NU}")
        assert (valor, conf) == (SP_NU, "alta")

    def test_a_plain_numeric_rg_is_accepted_when_labelled(self):
        """Not every state punctuates. A label is enough on its own."""
        valor, conf, _ = find_rg("CARTEIRA DE IDENTIDADE 1234567")
        assert (valor, conf) == ("1234567", "alta")

    def test_the_longest_matching_label_is_reported(self):
        """`IDENTIDADE` sits inside `CARTEIRA DE IDENTIDADE`.

        Reporting the short form would make the audit trail say the parser saw
        less than it did.
        """
        _, _, rotulo = find_rg(f"CARTEIRA DE IDENTIDADE {SP}")
        assert rotulo == "CARTEIRA DE IDENTIDADE"

    def test_accents_and_casing_do_not_matter(self):
        valor, conf, _ = find_rg(f"Cédula de Identidade: {SP}")
        assert (valor, conf) == (SP, "alta")


class TestUnlabelled:
    def test_the_fully_punctuated_shape_is_a_low_confidence_suggestion(self):
        """Dotted thousands AND a check character — the one self-evidence an
        RG carries."""
        valor, conf, rotulo = find_rg(f"SECRETARIA DE SEGURANCA PUBLICA {SP}")
        assert (valor, conf, rotulo) == (SP, "baixa", None)

    def test_bare_digits_with_no_label_are_rejected_outright(self):
        """🔴 The core rule. Not downgraded — rejected.

        A run of digits with neither a label nor RG punctuation is not
        evidence of anything, and a `baixa` here would put noise into the
        confirm queue on every document that contains a number.
        """
        assert find_rg("PROTOCOLO 52179965") == (None, "nenhuma", None)

    def test_dots_without_a_check_character_are_not_enough(self):
        assert find_rg("VALOR 52.179.965") == (None, "nenhuma", None)


class TestDecoys:
    def test_the_cpf_on_the_same_card_is_never_read_as_the_rg(self):
        """🔴 The failure this guard exists for.

        Both numbers are printed a line apart. Without the CPF-checksum
        discriminator, the CPF under an `RG` label is written as the RG — a
        well-formed, plausible, wrong value that overwrites a correct one.
        """
        assert find_rg(f"RG\n{CPF}") == (None, "nenhuma", None)

    def test_a_labelled_rg_survives_a_cpf_elsewhere_on_the_page(self):
        valor, conf, _ = find_rg(f"RG {SP}\nCPF {CPF}")
        assert (valor, conf) == (SP, "alta")

    def test_a_matricula_is_not_a_persons_rg(self):
        """This extractor also runs over an imóvel's documents."""
        assert find_rg("MATRICULA 187442") == (None, "nenhuma", None)

    def test_an_rg_inside_a_filiacao_block_is_demoted_not_trusted(self):
        """Same ambiguity as the CPF case — see `test_cpf.py` for the
        reasoning. The value survives at `baixa`, with no matched label
        reported, because what the label attaches to is precisely what is in
        doubt."""
        valor, conf, _ = find_rg(f"FILIACAO MARIA DE TAL RG {SP}")
        assert (valor, conf) == (SP, "baixa")

    def test_an_rg_squarely_inside_a_block_is_rejected(self):
        """No RG label after the block opener, and bare digits carry no
        self-evidence."""
        assert find_rg("FILIACAO MARIA DE TAL 52179965") == (None, "nenhuma", None)


class TestDisagreement:
    def test_two_different_labelled_rgs_report_absence(self):
        valor, conf, _ = find_rg(f"RG {SP}\nRG 11.222.333-4")
        assert (valor, conf) == (None, "nenhuma")

    def test_the_same_rg_punctuated_two_ways_is_agreement(self):
        """`only_alnum` is what makes these compare equal."""
        assert only_alnum(SP) == only_alnum(SP_NU)
        valor, conf, _ = find_rg(f"RG {SP}\nREGISTRO GERAL {SP_NU}")
        assert conf == "alta"
        assert only_alnum(valor) == only_alnum(SP)


class TestOrgaoExpedidor:
    def test_a_single_issuer_reads_high(self):
        assert find_rg_orgao(f"RG {SP} SSP/SP") == ("SSP/SP", "alta")

    def test_separators_are_normalised(self):
        assert find_rg_orgao("SSP-SP")[0] == "SSP/SP"
        assert find_rg_orgao("SSP SP")[0] == "SSP/SP"

    def test_a_non_ssp_issuer_is_read(self):
        assert find_rg_orgao("DETRAN/RJ") == ("DETRAN/RJ", "alta")

    def test_an_address_line_is_not_an_issuer(self):
        """A street ending in a city and UF is the common false positive."""
        assert find_rg_orgao("NATURAL DE SP") == (None, "nenhuma")

    def test_disagreement_returns_the_first_at_low_confidence(self):
        """🔴 The one place in this family where disagreement is not absence.

        The issuer is printed adjacent to the RG and later matches are almost
        always an address. Returning nothing would store an RG number with no
        issuer, which is itself an incomplete qualification on a contract.
        """
        valor, conf = find_rg_orgao("SSP/SP ... DETRAN/RJ")
        assert (valor, conf) == ("SSP/SP", "baixa")

    def test_nothing_when_there_is_no_issuer(self):
        assert find_rg_orgao(f"RG {SP}") == (None, "nenhuma")


class TestNothing:
    def test_empty_text(self):
        assert find_rg("") == (None, "nenhuma", None)
        assert find_rg_orgao("") == (None, "nenhuma")

    def test_a_document_with_no_rg(self):
        assert find_rg("NOME FULANO DE TAL SEXO MASCULINO") == (None, "nenhuma", None)
