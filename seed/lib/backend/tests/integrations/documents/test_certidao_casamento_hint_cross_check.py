"""`conjuges.find_conjuges`'s hint cross-check — when a label-driven
reader (`_ler_bloco_estruturado`, `_ler_narrativa_matrimonio`,
`_ler_rotulada`) DID find something, but names a spouse compatible with
NEITHER of the caller's hinted names, the label read is replaced OUTRIGHT
by `_ler_ancorada`'s own confirm-only read — even when that anchored read
is itself `()`.

🔴 THE PROBLEM THIS CLOSES — real, measured (P2 corpus, 2026-09-29)

On the P2 13-file corpus, `casamento_score_compare.py`'s own WRONG count
(a read spouse whose name matches NEITHER expected name) was 4/13 and
3/13 across two independent vision-transcription runs, on documents where
a label-driven reader DID recognise the layout and DID produce two names
— just not always the RIGHT two, because that run's own transcription
genuinely misread one spouse (an OCR-glitched verb hid the adoption
clause; a badly-scanned page garbled a name past recovery entirely).
"A label read SUCCEEDED" and "a label read is TRUSTWORTHY" are different
claims — see `find_conjuges`'s own docstring for why the anchored reader,
which can only ever CONFIRM a name the document itself prints, is always
safe to prefer once a conflict is detected: it can only remove a wrong
guess, never invent one.

The remaining corpus WRONG entry this file does NOT chase — a certidão's
own averbação naming a real second person (an ex-spouse) who is simply
not a party to THIS deal, with only a single-titular hint on file — is a
DELIBERATE non-fix: see `TestOnlyOneHintAlongsideAGenuinelyRealSecondPerson`
below for why "no opinion" about a second spouse must never be treated as
"this spouse is wrong".

Invented names/dates throughout; each shape mirrors a real masked
transcription finding from the corpus (never a real name).
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.conjuges import (
    _leitura_conflita_com_esperados,
    find_conjuges,
)

#: The ELE:/ELA: layout `test_certidao_casamento_rotulada_adocao.py`
#: already covers, but here the adoption clause's own verb is OCR-glitched
#: ("PASSOA" for "PASSOU") — invisible to ANY regex, root-cause fix
#: included. The bride's MAIDEN name (unrelated in spelling to her married
#: one — not merely missing a middle name) is all `_ler_rotulada` can
#: read; her actual married name is still printed, verbatim, in the same
#: clause `_ler_ancorada`'s own exact-text anchor can find directly.
CERTIDAO_VERBO_GLITCHED = (
    "CERTIDAO DE CASAMENTO\n"
    "ELE: RICARDO MOURA SILVA, nascido no dia dez de janeiro de mil "
    "novecentos e oitenta, filho de PEDRO MOURA SILVA e de ANA MOURA "
    "SILVA.\n"
    "ELA: PATRICIA ARAUJO PEREIRA, nascida no dia vinte de fevereiro de "
    "mil novecentos e oitenta e dois, filha de JOSE ARAUJO PEREIRA e de "
    "ROSA ARAUJO PEREIRA.\n"
    "Data da celebracao do casamento: 05/06/2010\n"
    "Regime de bens: comunhao parcial de bens\n"
    "Nome que cada um dos conjuges passou a utilizar (quando houver "
    "alteracao): ELE: continuou a usar o mesmo nome. ELA: passoa a usar "
    "o nome de PATRICIA COSTA LIMA.\n"
)
RICARDO_ESPERADO = "RICARDO MOURA SILVA"
PATRICIA_ESPERADA = "PATRICIA COSTA LIMA"


class TestVisionGlitchLeavesAWrongNameTheCrossCheckRecovers:
    def test_without_the_glitch_fix_the_maiden_name_conflicts_with_the_hint(
        self,
    ) -> None:
        """Root-cause guard: proves the fixture genuinely exercises a
        residual gap the regex overlay cannot see (an OCR-glitched verb),
        not a shape the overlay already fixes."""
        (_ricardo, patricia) = find_conjuges(CERTIDAO_VERBO_GLITCHED)
        assert patricia.nome == "PATRICIA ARAUJO PEREIRA"

    def test_the_hint_cross_check_recovers_the_married_name(self) -> None:
        ricardo, patricia = find_conjuges(
            CERTIDAO_VERBO_GLITCHED,
            esperados=(RICARDO_ESPERADO, PATRICIA_ESPERADA),
        )
        assert ricardo.nome == RICARDO_ESPERADO
        assert patricia.nome == PATRICIA_ESPERADA


#: A rotulada-recognised document where BOTH transcribed names are badly
#: garbled — plausible-looking, but nowhere close to the two real
#: (hinted) names, and neither hint anchors anywhere in this text either
#: (a genuinely unreadable scan, not a labelling accident).
CERTIDAO_GARBLED_BEYOND_RECOVERY = (
    "CERTIDAO DE CASAMENTO\n"
    "NOMES\n"
    "XYZQWERTY GARBLED NOMEZZZ\n"
    "ANOTHER BADLY READ NAME\n"
    "XYZQWERTY GARBLED NOMEZZZ, nascido no dia dez de janeiro de mil "
    "novecentos e setenta, filho de ALGUEM DA SILVA e de OUTRO ALGUEM.\n"
    "ANOTHER BADLY READ NAME, nascida no dia vinte de fevereiro de mil "
    "novecentos e setenta e dois, filha de FULANO DA SILVA e de CICLANA "
    "DA SILVA.\n"
    "Data da celebracao do casamento: 05/06/2000\n"
    "Regime de bens: comunhao parcial de bens\n"
)


class TestAWrongNameIsWorseThanAnEmptyOne:
    """When the anchored read ALSO finds nothing, the label read is still
    dropped — a wrong name must never survive simply because there was
    nothing better to replace it with."""

    def test_with_no_hints_the_garbled_names_are_returned_as_is(self) -> None:
        """Baseline: without a hint, historical behaviour is unchanged —
        `find_conjuges` has no way to know these names are wrong."""
        um, dois = find_conjuges(CERTIDAO_GARBLED_BEYOND_RECOVERY)
        assert um.nome == "XYZQWERTY GARBLED NOMEZZZ"
        assert dois.nome == "ANOTHER BADLY READ NAME"

    def test_with_hints_that_anchor_nowhere_the_result_is_empty_not_wrong(
        self,
    ) -> None:
        resultado = find_conjuges(
            CERTIDAO_GARBLED_BEYOND_RECOVERY,
            esperados=("REAL PERSON UM SILVA", "REAL PERSON DOIS PEREIRA"),
        )
        assert resultado == ()


#: The certidão genuinely names TWO real people — but only ONE of them
#: (the divorced vendor herself) is a party to THIS deal; the other is her
#: ex-husband, named on the SAME marriage certificate, irrelevant here.
CERTIDAO_COM_EX_CONJUGE = (
    "CERTIDAO DE CASAMENTO\n"
    "ELE: JOSE CARLOS BEZERRA, nascido no dia dez de janeiro de mil "
    "novecentos e setenta, filho de PEDRO BEZERRA e de ROSA BEZERRA.\n"
    "ELA: MARCIA REGINA ALBUQUERQUE, nascida no dia vinte de fevereiro de "
    "mil novecentos e setenta e dois, filha de ANTONIO ALBUQUERQUE e de "
    "LUIZA ALBUQUERQUE.\n"
    "Data da celebracao do casamento: 05/06/2000\n"
    "Regime de bens: comunhao parcial de bens\n"
    "Averbacao: divorciados em 10/10/2010 conforme sentenca judicial.\n"
)
MARCIA_ESPERADA = "MARCIA REGINA ALBUQUERQUE"


class TestOnlyOneHintAlongsideAGenuinelyRealSecondPerson:
    """`esperados` names only ONE person (a single-titular deal, no
    `conjuge_nome` on file) — the OTHER conjuge the certidão genuinely
    names is a real person, just not one this deal has any opinion about.

    🔴 THE CROSS-CHECK MUST NOT FIRE HERE — real, measured (P2 corpus,
    2026-09-29): a first version of `_leitura_conflita_com_esperados`
    checked "is this spouse compatible with ANY hint" with no regard for
    HOW MANY hints were supplied, so a genuinely correct second spouse
    (simply not covered by the caller's single hint) matched neither name
    in `esperados` and was misread as a conflict — discarding their real,
    correctly-attributed facts (birthdate, CPF, ...) on every two-spouse
    certidão a single-titular caller ever reads.
    `test_certidao_casamento_tabular_dn_not_misattributed.py` and
    `test_data_nascimento_casamento_plausibilidade.py`'s own single-hint
    fixtures caught this immediately. "No opinion" and "ruled out" are
    different claims — `_leitura_conflita_com_esperados` now refuses to
    judge a read with MORE spouses than the caller supplied hints for; see
    its own docstring."""

    def test_without_the_hint_both_real_people_are_returned(self) -> None:
        jose, marcia = find_conjuges(CERTIDAO_COM_EX_CONJUGE)
        assert jose.nome == "JOSE CARLOS BEZERRA"
        assert marcia.nome == MARCIA_ESPERADA

    def test_a_single_hint_still_returns_both_the_confirmed_and_the_unhinted_party(
        self,
    ) -> None:
        jose, marcia = find_conjuges(
            CERTIDAO_COM_EX_CONJUGE, esperados=(MARCIA_ESPERADA,)
        )
        assert jose.nome == "JOSE CARLOS BEZERRA"
        assert marcia.nome == MARCIA_ESPERADA


#: The SAME `CERTIDAO_ROTULADA` shape `test_certidao_casamento_ancorada.py`
#: already exercises for "the anchored fallback never runs when the label
#: path already succeeds" — reused here to prove the NEW conflict-check
#: does not misfire on a read that is already fully correct.
CERTIDAO_ROTULADA_CORRETA = """
CERTIDAO DE CASAMENTO
NOMES
JOAO PEREIRA LIMA
CARLA MENDES ROCHA
JOAO PEREIRA LIMA, nascido no dia dez de janeiro de mil novecentos e oitenta (10/01/1980), de nacionalidade brasileira, profissao engenheiro, filho de PEDRO LIMA e de ANA LIMA.
CARLA MENDES ROCHA, nascida no dia vinte de fevereiro de mil novecentos e oitenta e dois (20/02/1982), de nacionalidade brasileira, profissao medica, filha de MARCOS ROCHA e de LUCIA ROCHA.
Data da celebracao do casamento: 05/06/2010
Regime de bens: comunhao parcial de bens
"""


class TestNoConflictLeavesTheLabelDrivenReadUntouched:
    def test_a_correct_label_driven_read_is_identical_with_or_without_hints(
        self,
    ) -> None:
        sem_hint = find_conjuges(CERTIDAO_ROTULADA_CORRETA)
        com_hint = find_conjuges(
            CERTIDAO_ROTULADA_CORRETA,
            esperados=("JOAO PEREIRA LIMA", "CARLA MENDES ROCHA"),
        )
        assert sem_hint == com_hint

    def test_leitura_conflita_com_esperados_says_no_conflict(self) -> None:
        lido = find_conjuges(CERTIDAO_ROTULADA_CORRETA)
        assert _leitura_conflita_com_esperados(
            lido, ("JOAO PEREIRA LIMA", "CARLA MENDES ROCHA")
        ) is False

    def test_no_esperados_at_all_is_never_a_conflict(self) -> None:
        """Guard for the `esperados_validos` empty-list short-circuit: a
        caller passing no hint (the historical call shape) must never
        trigger the cross-check, whatever the label read contains."""
        lido = find_conjuges(CERTIDAO_GARBLED_BEYOND_RECOVERY)
        assert _leitura_conflita_com_esperados(lido, ()) is False


class TestLeituraConflitaComEsperadosDirectly:
    """Isolates the predicate itself, without the surrounding
    `find_conjuges` ladder."""

    def test_a_spouse_matching_neither_hint_is_a_conflict(self) -> None:
        from noctusai_lib.integrations.documents.conjuges import ConjugeLido

        lido = (
            ConjugeLido(nome="ALGUEM CORRETO SILVA"),
            ConjugeLido(nome="PESSOA TOTALMENTE ERRADA"),
        )
        assert _leitura_conflita_com_esperados(
            lido, ("ALGUEM CORRETO SILVA", "OUTRA PESSOA CERTA")
        ) is True

    def test_both_spouses_matching_some_hint_is_not_a_conflict(self) -> None:
        from noctusai_lib.integrations.documents.conjuges import ConjugeLido

        lido = (
            ConjugeLido(nome="ALGUEM CORRETO SILVA"),
            ConjugeLido(nome="OUTRA PESSOA CERTA"),
        )
        assert _leitura_conflita_com_esperados(
            lido, ("ALGUEM CORRETO SILVA", "OUTRA PESSOA CERTA")
        ) is False

    def test_an_empty_nome_anterior_only_slot_is_never_a_false_conflict(
        self,
    ) -> None:
        """A `ConjugeLido` with NEITHER `nome` nor `nome_anterior` set
        never happens in practice (`nome` is required), but the predicate
        must not crash or false-positive on a slot with nothing to
        compare — absence is not a wrong guess."""
        from noctusai_lib.integrations.documents.conjuges import ConjugeLido

        lido = (ConjugeLido(nome=""),)
        assert _leitura_conflita_com_esperados(lido, ("ALGUEM SILVA",)) is False
