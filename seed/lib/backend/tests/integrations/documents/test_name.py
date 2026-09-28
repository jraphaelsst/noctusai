"""The name parser, and specifically the ways it must REFUSE to answer.

A wrong birthdate is caught by a plausibility gate. A wrong name is not
catchable by anything: `MARIA APARECIDA DOS SANTOS` read off the FILIAÇÃO
line instead of the NOME line is a real, well-formed Brazilian name that
no downstream check can distinguish from the right answer. So most of
this file is about the parser declining.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.mrz import _mrz_check
from noctusai_lib.integrations.documents.name import (
    find_name,
    find_name_conflitos,
    looks_like_a_name,
)
from noctusai_lib.integrations.documents.text import normalize_lines, strip_accents_upper

#: An anonymised, structurally-faithful excerpt of a certidão de casamento's
#: `NOMES` holder block — see `civil_status.py`'s and `real.py`'s own
#: comments on the same real-scan defect this section regression-tests.
CERTIDAO_NOMES_LAYOUT = """
CERTIDAO DE CASAMENTO
NOMES
ALMIR TEIXEIRA DA COSTA
CPF
303.102.653-55
MARIANA PELLEGRINI RANGEL
CPF
478.982.096-30
MATRICULA
115568 01 55 2011 2 00198
"""


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


class TestCertidaoDeCasamentoMultiHolderHeader:
    """🔴 THE BUG THIS CLASS FIXES
    ------------------------------
    Before `_MULTI_HOLDER_LABELS`, the `_label_at` word-boundary rule that
    correctly rejects `NOMEACAO` matching `NOME` ALSO rejected the
    certidão's own plural header `NOMES` — so this parser found no name
    label at all on a real certidão de casamento and returned
    `(None, "nenhuma", None)`, indistinguishable from "the document doesn't
    carry a name". `find_name` still cannot choose between the two spouses
    (that decline is correct, see `TestAmbiguityIsReportedNotResolved`
    above) — but it must at least SEE both of them, and
    `find_name_conflitos` must be able to report which ones."""

    def test_the_plural_header_is_recognised_and_still_correctly_declines(self):
        assert find_name(CERTIDAO_NOMES_LAYOUT) == (None, "nenhuma", None)

    def test_conflitos_reports_both_spouses_by_name(self):
        conflitos = find_name_conflitos(CERTIDAO_NOMES_LAYOUT)
        assert conflitos == ["ALMIR TEIXEIRA DA COSTA", "MARIANA PELLEGRINI RANGEL"]

    def test_a_single_holder_under_the_plural_header_is_not_a_conflict(self):
        """Only ONE name follows `NOMES` — no ambiguity to report, and
        `find_name` should read it normally."""
        texto = "NOMES\nJOAO PEREIRA DA SILVA\nMATRICULA\n123456\n"
        assert find_name_conflitos(texto) is None
        value, confidence, label = find_name(texto)
        assert value == "JOAO PEREIRA DA SILVA"
        assert confidence == "alta"
        assert label == "NOMES"


class TestFindNameConflitosIsNoneWhenThereIsNoAmbiguity:
    def test_an_ordinary_absent_name_is_not_reported_as_a_conflict(self):
        """`find_name_conflitos` must not manufacture ambiguity out of plain
        absence — the ordinary "not on the document" case stays `None`."""
        assert find_name_conflitos("CPF 123.456.789-00\nNOME FULANO") is None
        assert find_name_conflitos("") is None

    def test_an_ordinary_single_holder_document_is_not_a_conflict(self):
        assert find_name_conflitos(
            "NOME: JOAO PEREIRA DA SILVA\nDATA DE NASCIMENTO: 12/05/1980\n"
        ) is None

    def test_two_disagreeing_nome_labels_are_reported_as_a_conflict_too(self):
        """The same underlying ambiguity `TestAmbiguityIsReportedNotResolved`
        already covers at the `find_name` level, now visible by name."""
        text = "NOME: JOAO PEREIRA DA SILVA\nNOME: CARLOS EDUARDO MENDES\n"
        assert find_name_conflitos(text) == [
            "CARLOS EDUARDO MENDES",
            "JOAO PEREIRA DA SILVA",
        ]


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


class TestNomeAdotadoPronomeLabels:
    """🔴 THE LAYOUT VARIANT THIS CLASS COVERS
    -------------------------------------------------------------
    A certidão de casamento's "nome que passou a adotar" clause states each
    spouse's post-marriage name under the PRONOUN (`Ele:` / `Ela:`), not
    `NOME` — invisible to `_candidatos` before `_PRONOUN_NAME_LABELS`
    existed, exactly like the plural `NOMES` header once was (see
    `TestCertidaoDeCasamentoMultiHolderHeader`'s own header). Unlike `NOME`,
    `ELE`/`ELA` are ordinary Portuguese words — `AQUELE`, `PELA`, `JANELA`
    all contain one verbatim — so this class also regression-tests the two
    guards that make recognising them safe: an explicit separator, and a
    word-boundary check that now applies to every label, not just these two.
    """

    TEXTO = (
        "CERTIDAO DE CASAMENTO\n"
        "NOME QUE CADA UM DOS CONJUGES PASSA A USAR EM RAZAO DO CASAMENTO\n"
        "Ele: JOAO PEREIRA DA SILVA\n"
        "Ela: MARIA SOUZA DA SILVA\n"
    )

    def test_both_spouses_are_read_as_a_conflict(self):
        assert find_name_conflitos(self.TEXTO) == [
            "JOAO PEREIRA DA SILVA", "MARIA SOUZA DA SILVA",
        ]

    def test_find_name_still_declines_between_the_two(self):
        assert find_name(self.TEXTO) == (None, "nenhuma", None)

    def test_a_single_pronoun_labelled_name_is_read_normally(self):
        texto = "Ele: CARLOS EDUARDO MENDES\n"
        assert find_name(texto) == ("CARLOS EDUARDO MENDES", "alta", "ELE")

    @pytest.mark.parametrize(
        "texto",
        [
            # No separator after the pronoun — ordinary prose, not a label.
            "ELE COMPARECEU PERANTE O OFICIAL\nELA TAMBEM COMPARECEU HOJE\n",
            # `ELE`/`ELA` starting mid-word — the word-boundary rule that
            # already protects `NOME` from `NOMEACAO` now protects these too.
            "AQUELE HOMEM CHEGOU CEDO\n",
            "PELA JANELA VIU O CEU AZUL\n",
            "DAQUELA VEZ EM DIANTE\n",
        ],
    )
    def test_ordinary_portuguese_words_never_become_a_label(self, texto):
        assert find_name(texto) == (None, "nenhuma", None)
        assert find_name_conflitos(texto) is None


class TestNomeAtualDosConjugesHeader:
    """Newer CRC certidão layout (structure from a real document, names
    invented): the spouses' block is headed "Nome atual dos cônjuges" and
    both CPFs follow under ONE "Número do CPF" label."""

    TEXTO = (
        "CERTIDÃO DE CASAMENTO\n\nNome atual dos cônjuges\n\n"
        "JOAO PEREIRA DA SILVA\n\nMARIA SOUZA DA SILVA\n\n"
        "Número do CPF\n\n412.954.238-98\n\n303.102.653-55\n\nMatrícula\n\n"
        "122788 01 55 2008 3 00017 077 0004843 71\n"
    )

    def test_the_heading_tail_is_never_read_as_a_name(self):
        valor, _, _ = find_name(self.TEXTO)
        assert valor != "ATUAL DOS CONJUGES"

    def test_both_spouses_are_the_named_conflict(self):
        assert find_name_conflitos(self.TEXTO) == [
            "JOAO PEREIRA DA SILVA", "MARIA SOUZA DA SILVA",
        ]

    def test_a_cpf_label_is_not_name_shaped(self):
        assert looks_like_a_name("Número do CPF") is False


class TestTrailingCitationClause:
    """A name-shaped line with a registry citation or a same-row field
    label glued onto its TAIL — real, measured 2026-09-23 — must not be
    thrown away whole for a formatting accident. See `name.
    _strip_trailing_citation`."""

    def test_a_livro_folha_termo_citation_on_the_same_line_is_trimmed(self):
        # Structure from a real certidão averbação (names invented): the
        # spouse's post-marriage name and the averbação's own registry
        # citation land on ONE transcribed line.
        texto = (
            "NOME QUE CADA UM DOS CONJUGES PASSOU A UTILIZAR\n"
            "ELA: FULANA DE TAL SILVA LIVRO B-123 FOLHA 45 TERMO 6789\n"
        )
        valor, confianca, rotulo = find_name(texto)
        assert valor == "FULANA DE TAL SILVA"
        assert confianca == "alta"

    def test_a_same_row_cpf_header_tail_is_trimmed_under_nomes(self):
        # Structure from a real certidão's wide `NOMES` holder table (names
        # invented): the NEXT column's `CPF` header lands on the same
        # visual row as the first holder's name, joined onto one OCR line.
        # Was `find_name_conflitos` returning ZERO candidates before this
        # fix (2026-09-23) — the whole line failed `looks_like_a_name`
        # outright because it contained the word "CPF".
        texto = (
            "NOMES\n"
            "FULANO DE TAL SANTOS                          CPF\n"
            "                                          042.654.468-95\n"
            "CICLANA DE TAL PEREIRA                        CPF\n"
            "                                          041.333.248-97\n"
            "MATRICULA\n"
            "1155568 01 55 2011 2 00198 278 0059433-91\n"
        )
        assert find_name_conflitos(texto) == [
            "CICLANA DE TAL PEREIRA", "FULANO DE TAL SANTOS",
        ]

    def test_trimming_an_all_institutional_line_still_finds_nothing(self):
        from noctusai_lib.integrations.documents.name import _strip_trailing_citation

        # No real name survives the trim — the line stays rejected, not
        # silently promoted to an empty-string "name".
        assert looks_like_a_name(
            _strip_trailing_citation("LIVRO FOLHA TERMO")
        ) is False


class TestAsteriskWrappedValue:
    """A cartório template that wraps every printed value in a footnote
    asterisk — real, measured 2026-09-23 (`* NOME COMPLETO *`). Neither
    edge is a name character, so without trimming it the whole line failed
    the shape check even though the name inside it is well-formed."""

    def test_a_name_wrapped_in_asterisks_under_nomes_is_found(self):
        texto = (
            "NOMES:\n"
            "* FULANO DE TAL SANTOS *\n"
            "* CICLANA DE TAL PEREIRA *\n"
            "MATRICULA:\n"
            "119222 01 55 2017 2 00093 208 0027875-91\n"
        )
        assert find_name_conflitos(texto) == [
            "CICLANA DE TAL PEREIRA", "FULANO DE TAL SANTOS",
        ]


class TestMultiHolderCollectorSkipsAnyCpfLabelRow:
    """🔴 THE BUG THIS CLASS FIXES — real, measured (P1/883, 2026-09-28)

    `_coleta_titulares_multiplos` used to skip a same-row-CPF interleave
    ONLY when the row was the exact text `CPF` (or the bare digits). A real
    certidão's own field header instead read `NUMERO DO CPF` on its own
    row between the two names — neither name-shaped nor an exact `"CPF"`
    match — so the collector stopped after the FIRST nubente and returned
    just one, unopposed candidate. `find_name` then wrote that one
    person's name with `"alta"` confidence, silently onto whichever card
    happened to ask, with no signal anything had gone wrong: the two-
    holder case degraded into the single-holder case by accident, not by
    the document only naming one person.
    """

    def test_a_labelled_cpf_row_other_than_the_bare_word_does_not_stop_the_scan(self):
        texto = (
            "NOME ATUAL DOS CONJUGES\n"
            "FULANO DE TAL SANTOS\n"
            "NUMERO DO CPF\n"
            "042.654.468-95\n"
            "CICLANA DE TAL PEREIRA\n"
            "NUMERO DO CPF\n"
            "041.333.248-97\n"
            "MATRICULA\n"
            "115568 01 55 2011 2 00198\n"
        )
        assert find_name_conflitos(texto) == [
            "CICLANA DE TAL PEREIRA", "FULANO DE TAL SANTOS",
        ]
        # Two co-equal holders, same as ever: still correctly declines to
        # pick one unattended.
        assert find_name(texto) == (None, "nenhuma", None)

    def test_a_bare_n_do_cpf_row_is_recognised_too(self):
        texto = (
            "NOMES\n"
            "FULANO DE TAL SANTOS\n"
            "Nº DO CPF\n"
            "042.654.468-95\n"
            "CICLANA DE TAL PEREIRA\n"
            "Nº DO CPF\n"
            "041.333.248-97\n"
        )
        assert find_name_conflitos(texto) == [
            "CICLANA DE TAL PEREIRA", "FULANO DE TAL SANTOS",
        ]

    def test_the_bare_cpf_row_still_works_unchanged(self):
        """The original, narrower shape must keep working — this is a
        widening of the skip condition, not a replacement of it."""
        texto = (
            "NOMES\n"
            "FULANO DE TAL SANTOS\n"
            "CPF\n"
            "042.654.468-95\n"
            "CICLANA DE TAL PEREIRA\n"
            "CPF\n"
            "041.333.248-97\n"
        )
        assert find_name_conflitos(texto) == [
            "CICLANA DE TAL PEREIRA", "FULANO DE TAL SANTOS",
        ]

    def test_a_long_line_that_merely_mentions_cpf_still_stops_the_scan(self):
        """The skip is for a SHORT administrative label row, not any line
        that happens to contain the word — a long sentence must still end
        the multi-holder collection where it always did."""
        texto = (
            "NOMES\n"
            "FULANO DE TAL SANTOS\n"
            "O CPF DE CADA CONTRAENTE FOI CONFERIDO PELO OFICIAL DO REGISTRO CIVIL\n"
            "CICLANA DE TAL PEREIRA\n"
        )
        # The long sentence line is neither name-shaped nor a short CPF
        # label row, so the collector stops there — only the first
        # nubente is collected under this header, same as before this fix.
        assert find_name_conflitos(texto) is None
        assert find_name(texto) == ("FULANO DE TAL SANTOS", "alta", "NOMES")


class TestTabularLabelRowIsNotANubente:
    """A tabular certidão can put a per-field label row (`DATA DE
    NASCIMENTO`) directly after the `NOMES` block. It is name-SHAPED, and was
    collected as a THIRD holder — which pushed the document off
    `conjuges.find_conjuges`'s exactly-two path (2026-09-28)."""

    def test_label_row_after_the_names_block_is_not_collected(self) -> None:
        from noctusai_lib.integrations.documents.name import find_name_conflitos

        texto = (
            "NOMES\n\nFULANO DE TAL SANTOS\n\nNUMERO DO CPF\n111.222.333-44\n\n"
            "CICLANA DE TAL PEREIRA\n\nNUMERO DO CPF\n555.666.777-88\n\n"
            "DATA DE NASCIMENTO\n04 10 1961\n"
        )
        assert sorted(find_name_conflitos(texto)) == [
            "CICLANA DE TAL PEREIRA",
            "FULANO DE TAL SANTOS",
        ]

    def test_nascimento_as_a_surname_is_still_a_name(self) -> None:
        from noctusai_lib.integrations.documents.name import looks_like_a_name

        assert looks_like_a_name("MARIA DO NASCIMENTO")
        assert not looks_like_a_name("DATA DE NASCIMENTO")


# ─── MRZ corroboration (real, measured, P1/883, 2026-09-28) ────────────────
#
# A CNH-e's vision transcription wrote the holder's name under the WRONG
# label: the card prints "1 NOME" right beside "1ª HABILITAÇÃO", and the
# model attributed the name to the latter. `find_name` found nothing under
# that mislabelling — the same shape this whole module's docstring already
# describes for FILIAÇÃO — except the document also carries an ICAO TD1 MRZ,
# whose line 3 is the name field. Every name below is invented.


def _linha_mrz_2(nascimento: str = "990101", validade: str = "300101") -> str:
    """A check-digit-verified TD1 MRZ line 2 (dates + sex + expiry +
    nationality) — the anchor `mrz.line2_indices` looks for. Same
    construction `test_identity_new_fields.py` already uses for
    `gender.py`'s own MRZ test."""
    return (
        f"{nascimento}{_mrz_check(nascimento)}F"
        f"{validade}{_mrz_check(validade)}BRA<<<<<<<<<<<0"
    )


class TestMrzCorroboratesAMislabelledName:
    """The exact production shape: a name sitting under a WRONG label, with
    a genuine MRZ elsewhere on the same card."""

    def test_mislabelled_name_corroborated_by_mrz_is_found_at_media(self) -> None:
        texto = f"""CARTEIRA NACIONAL DE HABILITACAO
1a HABILITACAO: ENZO DE OLIVEIRA SANTOS
CATEGORIA B
{_linha_mrz_2()}
ENZ0<<DE<<OLIVEIRA<<SANTOS<<<<<<<
"""
        assert find_name(texto) == (
            "ENZO DE OLIVEIRA SANTOS",
            "media",
            "MRZ (corroborado)",
        )

    def test_digit_for_letter_ocr_slip_in_the_mrz_itself_does_not_block_it(
        self,
    ) -> None:
        # The `0` standing in for an `O` in `ENZ0` is the OCR slip measured
        # in production — the fix's own digit->letter table must still find
        # the corroborating value even though the MRZ line itself is wrong.
        texto = f"""CARTEIRA NACIONAL DE HABILITACAO
1a HABILITACAO: ENZO DE OLIVEIRA SANTOS
{_linha_mrz_2()}
ENZ0<<DE<<OLIVEIRA<<SANTOS<<<<<<<
"""
        assert find_name(texto)[0] == "ENZO DE OLIVEIRA SANTOS"
        assert find_name(texto)[1] == "media"


class TestMrzTruncatedWithNoCorroboration:
    """A truncated MRZ name field is too risky to trust alone (ICAO's own
    30-character field width may have cut the last name off mid-word)."""

    def test_truncated_mrz_alone_with_no_corroborating_line_is_none(self) -> None:
        # No trailing `<` padding: the field fills its full width, so it
        # may be cut off mid-word.
        linha3_truncada = "ENZ0<<DE<<OLIVEIRA<<SANTOSISSIMOOOOOOOOOOOOOO"
        texto = f"""CARTEIRA NACIONAL DE HABILITACAO
CATEGORIA B
{_linha_mrz_2()}
{linha3_truncada}
"""
        assert find_name(texto) == (None, "nenhuma", None)

    def test_untruncated_mrz_alone_with_no_corroboration_is_a_baixa_guess(
        self,
    ) -> None:
        # Trailing `<` padding: the field did NOT run out of room, so the
        # MRZ's own reading is worth a low-confidence guess on its own.
        texto = f"""DOCUMENTO
{_linha_mrz_2()}
ENZ0<<DE<<OLIVEIRA<<SANTOS<<<<<<<
"""
        assert find_name(texto) == ("ENZO DE OLIVEIRA SANTOS", "baixa", "MRZ")


class TestMrzAgreementAndDisagreementWithALabelledName:
    def test_labelled_nome_agreeing_with_mrz_keeps_its_normal_confidence(
        self,
    ) -> None:
        texto = f"""CARTEIRA NACIONAL DE HABILITACAO
NOME: ENZO DE OLIVEIRA SANTOS
{_linha_mrz_2()}
ENZ0<<DE<<OLIVEIRA<<SANTOS<<<<<<<
"""
        assert find_name(texto) == ("ENZO DE OLIVEIRA SANTOS", "alta", "NOME")

    def test_labelled_nome_disagreeing_with_mrz_is_only_a_suggestion(self) -> None:
        """A real disagreement demotes the labelled value to `baixa` (a human
        confirms) — the MRZ is a vision read too and cannot veto the label."""
        texto = f"""CARTEIRA NACIONAL DE HABILITACAO
NOME: MARIA DA SILVA PEREIRA
{_linha_mrz_2()}
ENZ0<<DE<<OLIVEIRA<<SANTOS<<<<<<<
"""
        assert find_name(texto) == ("MARIA DA SILVA PEREIRA", "baixa", "NOME")

    def test_a_one_letter_mrz_misread_still_agrees(self) -> None:
        """P2 corpus, 2026-09-28: the MRZ read one letter off (a vision slip)
        must not demote or erase a correctly labelled NOME."""
        texto = f"""CARTEIRA NACIONAL DE HABILITACAO
NOME: ENZO DE OLIVEIRA SANTOS
{_linha_mrz_2()}
ENZ0<<DE<<OLIVEIRO<<SANTOS<<<<<<<
"""
        assert find_name(texto) == ("ENZO DE OLIVEIRA SANTOS", "alta", "NOME")


class TestNomeDeslocadoPara1aHabilitacao:
    """P2 corpus, 2026-09-28: 4/9 CNH-e scans came back with the name under
    "1ª HABILITAÇÃO" (a date field) and no NOME row."""

    def test_name_under_1a_habilitacao_on_a_cnh(self) -> None:
        texto = """CARTEIRA NACIONAL DE HABILITAÇÃO / DRIVER LICENSE
1ª HABILITAÇÃO: FULANO DE TAL SANTOS
3 DATA, LOCAL E UF DE NASCIMENTO: 01/02/1980, SAO PAULO, SP
"""
        assert find_name(texto) == ("FULANO DE TAL SANTOS", "media", "1ª HABILITAÇÃO (nome deslocado)")

    def test_a_real_date_there_is_not_a_name(self) -> None:
        texto = """CARTEIRA NACIONAL DE HABILITAÇÃO
1ª HABILITAÇÃO: 12/03/2001
"""
        assert find_name(texto) == (None, "nenhuma", None)

    def test_only_on_a_cnh(self) -> None:
        texto = """CERTIFICADO DE HABILITACAO PROFISSIONAL
HABILITACAO: FULANO DE TAL SANTOS
"""
        assert find_name(texto) == (None, "nenhuma", None)


class TestCertidaoWithNoMrzIsUnaffected:
    """A certidão de casamento carries no MRZ at all — every branch added
    for MRZ corroboration must be a complete no-op on it."""

    def test_certidao_multi_holder_behaviour_is_unchanged(self) -> None:
        assert find_name(CERTIDAO_NOMES_LAYOUT) == (None, "nenhuma", None)
        assert sorted(find_name_conflitos(CERTIDAO_NOMES_LAYOUT)) == [
            "ALMIR TEIXEIRA DA COSTA",
            "MARIANA PELLEGRINI RANGEL",
        ]


class TestBilingualCnhLabel:
    """2022+ CNH: "NOME E SOBRENOME / NAME AND SURNAME: <name>" (P2, 2026-09-28)."""

    def test_bilingual_label_reads_the_name(self) -> None:
        texto = "CARTEIRA NACIONAL DE HABILITAÇÃO\n2. NOME E SOBRENOME / NAME AND SURNAME: FULANO DE TAL SANTOS\n"
        assert find_name(texto)[0] == "FULANO DE TAL SANTOS"
