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

from noctusai_lib.integrations.documents import find_rg, find_rg_orgao, is_same_as_cpf
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


class TestDvSeparatorWhitespaceIsNoiseNotSignal:
    """P1/883 live bug (2026-09-24), a real image-only CNH: "DOC.
    IDENTIDADE: 13.032.360 - 3" (a space either side of the DV's dash — a
    routine vision-transcription artifact) missed the punctuated alternative
    entirely, fell through to the plain-digits one, and read as
    `13.032.360` — the DV silently dropped."""

    def test_a_space_either_side_of_the_dash_is_collapsed(self):
        valor, conf, _ = find_rg("DOC. IDENTIDADE: 13.032.360 - 3 SSP SP")
        assert (valor, conf) == ("13.032.360-3", "alta")

    def test_a_space_before_the_dash_only(self):
        valor, _, _ = find_rg("DOC. IDENTIDADE: 13.032.360 -3 SSP SP")
        assert valor == "13.032.360-3"

    def test_a_space_after_the_dash_only(self):
        valor, _, _ = find_rg("DOC. IDENTIDADE: 13.032.360- 3 SSP SP")
        assert valor == "13.032.360-3"

    def test_the_bare_digit_shape_gets_the_same_treatment(self):
        valor, _, _ = find_rg("DOC. IDENTIDADE: 13032360 - 3 SSP SP")
        assert valor == "13032360-3"

    def test_no_regression_on_the_tight_form(self):
        valor, _, _ = find_rg("DOC. IDENTIDADE: 13.032.360-3 SSP SP")
        assert valor == "13.032.360-3"


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


class TestOrgaoJurisdictionContextIsNotAnIssuer:
    """🔴 A FABRICATED ISSUER SEEN ON A REAL CERTIDÃO DE CASAMENTO
    ---------------------------------------------------------------
    "Comarca de Cotia/SP" is the jurisdiction of the notary's office that
    produced the document — an address, not who issues an RG. The document
    carried no RG at all, yet this shape-only regex matched `COTIA` bound to
    `SP` and returned a fabricated `rg_orgao`. `COTIA` itself cannot be
    blocklisted (it is an ordinary place name with no other reason to be
    rejected) — only the CONTEXT immediately before it tells the two apart."""

    def test_comarca_de_is_not_read_as_an_issuer(self):
        assert find_rg_orgao("COMARCA DE COTIA/SP") == (None, "nenhuma")

    def test_tabelionato_de_is_not_read_as_an_issuer(self):
        assert find_rg_orgao("TABELIONATO DE NOTAS DO DISTRITO DE MOGI/SP") == (
            None,
            "nenhuma",
        )

    def test_cartorio_de_is_not_read_as_an_issuer(self):
        assert find_rg_orgao("CARTORIO DE REGISTRO CIVIL DE COTIA/SP") == (
            None,
            "nenhuma",
        )

    def test_a_real_issuer_elsewhere_in_the_same_document_still_reads(self):
        """The jurisdiction guard must not blanket-reject the WHOLE
        document — only the match immediately preceded by a jurisdiction
        word."""
        valor, conf = find_rg_orgao("RG 12.345.678-9 SSP/SP ... COMARCA DE COTIA/SP")
        assert (valor, conf) == ("SSP/SP", "alta")


class TestNothing:
    def test_empty_text(self):
        assert find_rg("") == (None, "nenhuma", None)
        assert find_rg_orgao("") == (None, "nenhuma")

    def test_a_document_with_no_rg(self):
        assert find_rg("NOME FULANO DE TAL SEXO MASCULINO") == (None, "nenhuma", None)


class TestLabelledCandidateSurvivesTheCpfShapeGuard:
    """🔴 THE NEW-MODEL CNH/CIN CASE — real, measured 2026-09-23.

    A "CNH Digital" field prints `44886493866 SP` under `DOC IDENTIDADE /
    ORG. EMISSOR / UF` — eleven digits that are ALSO, verbatim, the same
    holder's own valid CPF (issuer `IIGDR`, the instant-identity
    convention). Before this fix, `_e_um_cpf`'s guard ran for EVERY
    candidate regardless of label and silently dropped this one — a real,
    well-evidenced, explicitly-labelled RG. The guard still protects the
    UNLABELLED case (`TestDecoys`, above) exactly as before.
    """

    #: A real holder's CPF, reused verbatim as the "DOC IDENTIDADE" value —
    #: this is the actual CIN/IIGDR shape, not a copy-paste data-entry
    #: error (see `is_same_as_cpf`'s own docstring on that distinction).
    CPF_COMO_RG = "44886493866"

    def test_a_labelled_identity_number_equal_to_a_valid_cpf_is_kept(self):
        texto = f"DOC IDENTIDADE / ORG. EMISSOR / UF\n{self.CPF_COMO_RG} SP"
        valor, conf, rotulo = find_rg(texto)
        assert valor == self.CPF_COMO_RG
        assert conf == "alta"

    def test_the_kept_value_is_flagged_same_as_cpf_for_a_downstream_confirm(self):
        # This module never refuses the write — it hands the caller enough
        # to ask for a human confirm, same posture `is_same_as_cpf`'s own
        # docstring documents.
        assert is_same_as_cpf(self.CPF_COMO_RG, "448.864.938-66") is True

    def test_an_unlabelled_eleven_digit_cpf_still_never_becomes_an_rg(self):
        # The widened `_RG_RE` upper bound (5-11) does not, on its own,
        # reopen the unlabelled guard — `_e_um_cpf` still runs for a
        # candidate with no RG label anchoring it at all.
        assert find_rg(f"OBSERVACOES\n{self.CPF_COMO_RG}") == (None, "nenhuma", None)


class TestOrgaoBirthplaceContextIsNotAnIssuer:
    """🔴 A CNH's OWN BIRTHPLACE FIELD MISREAD AS THE ISSUING BODY — real,
    measured 2026-09-23. "16/02/1997 SAO PAULO/SP" sits under "DATA, LOCAL
    E UF DE NASCIMENTO" — a place the holder was BORN, not who issued the
    card — yet the shape-only issuer scan matched `PAULO` bound to `SP` and
    returned a fabricated `rg_orgao`, exactly the `TestOrgaoJurisdiction
    ContextIsNotAnIssuer` class above documents for a cartório's own
    COMARCA/TABELIONATO address."""

    def test_a_birthplace_city_under_nascimento_is_not_read_as_an_issuer(self):
        assert find_rg_orgao(
            "DATA, LOCAL E UF DE NASCIMENTO\n16/02/1997 SAO PAULO/SP"
        ) == (None, "nenhuma")

    def test_naturalidade_context_is_also_excluded(self):
        assert find_rg_orgao("NATURALIDADE SAO PAULO/SP") == (None, "nenhuma")

    def test_a_real_issuer_elsewhere_still_reads_through_the_birthplace(self):
        texto = (
            "DATA, LOCAL E UF DE NASCIMENTO\n16/02/1997 SAO PAULO/SP\n"
            "DOC IDENTIDADE / ORG. EMISSOR / UF\n13032360 SSP/SP\n"
        )
        assert find_rg_orgao(texto) == ("SSP/SP", "alta")


class TestIsSameAsCpf:
    """The real-contract bug: an RG field carrying the CPF verbatim."""

    def test_flags_the_exact_copy(self):
        assert is_same_as_cpf(CPF, CPF) is True

    def test_flags_regardless_of_punctuation_on_either_side(self):
        assert is_same_as_cpf("41295423898", CPF) is True
        assert is_same_as_cpf(CPF, "41295423898") is True

    def test_a_real_rg_is_not_flagged(self):
        assert is_same_as_cpf(SP, CPF) is False

    def test_missing_either_value_is_not_a_match(self):
        assert is_same_as_cpf(None, CPF) is False
        assert is_same_as_cpf(SP, None) is False
        assert is_same_as_cpf(None, None) is False
        assert is_same_as_cpf("", CPF) is False


class TestOrgaoAnchoredToTheNumber:
    """The issuer printed beside the RG beats an issuer-SHAPED place name
    earlier on the card. Layout from a real CNH vision transcript
    (names invented): field 3 carries "SAO PAULO/SP" above field 4c."""

    CNH = (
        "2 e 1 NOME E SOBRENOME\nMARIA DAS DORES TESTE\n"
        "3 DATA, LOCAL E UF DE NASCIMENTO\n20/04/1964 SAO PAULO/SP\n"
        "4c DOC. IDENTIDADE / ÓRG. EMISSOR / UF\n13032360 SSP/SP\n"
        "4d CPF\n041.333.248-97\n"
    )

    def test_the_cnh_issuer_is_the_one_next_to_the_number(self):
        rg, _, _ = find_rg(self.CNH)
        assert rg == "13032360"
        assert find_rg_orgao(self.CNH, rg) == ("SSP/SP", "alta")

    def test_without_the_number_shape_scan_skips_the_birthplace(self):
        # 2026-09-23: "SAO PAULO/SP" sits in a `NASCIMENTO` (birthplace)
        # field, not an issuing-body one — `_ORGAO_CONTEXTO_JURISDICAO` now
        # excludes it here too, same as it already excluded a cartório's
        # own COMARCA/TABELIONATO address. Only the genuine issuer-shaped
        # token (`SSP/SP`, field 4c) survives the shape scan, so a caller
        # with no RG hint gets the right answer at `alta` instead of a
        # birthplace city mistaken for the issuing body at `baixa`.
        assert find_rg_orgao(self.CNH) == ("SSP/SP", "alta")

    def test_dash_separated_pair_on_a_qualification_line(self):
        texto = "portador do RG 13.032.360-3 - SSP-SP e CPF 041.333.248-97"
        assert find_rg_orgao(texto, "13.032.360-3") == ("SSP/SP", "alta")

    def test_a_word_between_number_and_issuer_is_not_adjacency(self):
        texto = "RG 13032360 NATURAL DE SAO PAULO/SP"
        # Falls back to the shape scan: a single issuer-shaped token, so the
        # pre-existing rule decides — adjacency never claimed it.
        from noctusai_lib.integrations.documents.rg import normalize, _orgao_adjacente

        assert _orgao_adjacente(normalize(texto), "13032360") is None


class TestOrgaoLabelledColumnBox:
    """P1/883 (2026-09-25), real: a CNH-e's own `DOC. IDENTIDADE / ÓRG.
    EMISSOR / UF` box transcribes as THREE separate labelled lines — not the
    single `13032360 SSP/SP` line `TestOrgaoAnchoredToTheNumber` covers —
    once the vision call actually receives `_IDENTITY_DOCUMENT_PROMPT`'s
    "one RÓTULO: valor per line" instruction (see
    `media.real_adapter.RealMediaResolver._doc_prompt_override`). Neither
    `_orgao_adjacente` (nothing touches the RG number) nor the bare shape
    scan (the acronym and the UF are two separate labelled tokens, never
    adjacent) can see this; `_orgao_rotulado` is the fix."""

    CNH_E = (
        "DOC. IDENTIDADE: 13032360\n"
        "ÓRG. EMISSOR: SSP\n"
        "UF: SP\n"
    )

    def test_acronym_and_uf_as_two_separate_labelled_sub_fields(self):
        assert find_rg_orgao(self.CNH_E) == ("SSP/SP", "alta")

    def test_also_resolves_when_find_rg_s_own_reading_is_passed_in(self):
        rg, _, _ = find_rg(self.CNH_E)
        assert rg == "13032360"
        assert find_rg_orgao(self.CNH_E, rg) == ("SSP/SP", "alta")

    def test_uf_printed_inline_after_the_acronym_still_works(self):
        texto = "ORG EMISSOR: SSP/SP"
        assert find_rg_orgao(texto) == ("SSP/SP", "alta")

    def test_orgao_abbreviation_without_the_accent_or_period(self):
        texto = "ORGAO EMISSOR: DETRAN\nUF: RJ"
        assert find_rg_orgao(texto) == ("DETRAN/RJ", "alta")

    def test_no_label_at_all_still_reports_nothing(self):
        assert find_rg_orgao("um texto qualquer sem nenhum rotulo") == (
            None,
            "nenhuma",
        )

    def test_a_decoy_word_right_after_the_label_is_rejected(self):
        # "EM" is in `_ORGAO_NAO` — a real acronym never legitimately reads
        # as one of the address/jurisdiction decoy words.
        texto = "ORG EMISSOR: EM ALGUM LUGAR"
        assert find_rg_orgao(texto) == (None, "nenhuma")
