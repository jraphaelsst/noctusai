"""`conjuges._ler_rotulada`'s own name-adoption overlay, and the
regex-precedence bug this work found and closed alongside it.

🔴 THE BUGS THIS FILE CLOSES — real, measured (P2 corpus, 2026-09-29)

1. **The ELE:/ELA: adoption clause is invisible to `_ler_rotulada`.** The
   CNJ-modern layout this reader recognises via `find_name_conflitos`
   states each spouse's PRE-MARRIAGE qualification under `ELE:`/`ELA:`
   ("ELE: FULANO, nascido ...") — the SAME two pronoun labels the
   certidão's own "NOME QUE CADA UM DOS CÔNJUGES PASSOU A UTILIZAR" clause
   restates further down ("ELA: PASSOU A USAR O NOME DE ..."). `name.
   _candidatos`'s pronoun-label collector has no notion of "second
   occurrence, different section": the adoption clause's own "PASSOU A
   USAR O NOME DE" prefix pushes the word count past `name.MAX_WORDS` (8),
   so it silently fails `looks_like_a_name` and never becomes a second
   candidate to conflict with — `_ler_rotulada` kept whichever `ELE:`/
   `ELA:` value validated, which was ALWAYS the qualification (maiden)
   one. A spouse whose certidão states a genuine name change was then
   reported under their MAIDEN name — wrong, not merely incomplete
   (P2/884). Closed by reading the SAME clause `_ler_bloco_estruturado`'s
   own `_NOME_ATUAL_CONJUGE_RE` and `_ler_narrativa_matrimonio`'s own
   `_ADOCAO_MASC_RE`/`_ADOCAO_FEM_RE` already read independently for
   THEIR OWN layouts.

2. **A bare, unanchored `|` inside `_ADOCAO_VERBO`.** `_ADOCAO_VERBO` is a
   top-level alternation (`X|Y`), and every EXISTING call site built its
   own regex as `PREFIXO + _ADOCAO_VERBO` — which `|` (binding weaker than
   concatenation) reads as `(PREFIXO seen only by the FIRST branch) |
   (the CONTINUA/CONTINUOU branch, matched ANYWHERE, prefix-free)`. A
   stray "continuou a assinar ..." on a witness's own paragraph, an
   averbação about an entirely different marriage, or anywhere else on the
   page matched just as well as the genuine clause and could silently
   overwrite a spouse's correct name with someone else's. This affected
   BOTH the pre-existing `_ADOCAO_MASC_RE`/`_ADOCAO_FEM_RE`
   (`_ler_narrativa_matrimonio`) and the new `_ADOCAO_ELE_RE`/
   `_ADOCAO_ELA_RE` this same fix introduces — every site now wraps
   `_ADOCAO_VERBO` in `(?:...)` so the prefix gates BOTH branches.

Invented names/dates throughout.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.conjuges import (
    _ADOCAO_ELA_RE,
    _ADOCAO_ELE_RE,
    find_conjuges,
)

#: The exact shape measured on the P2 corpus (884, comprador side): a
#: clean `ELE:`/`ELA:` qualification pair, followed by a SEPARATE
#: "NOME QUE CADA UM DOS CONJUGES PASSOU A UTILIZAR" clause restating both
#: pronouns for the marriage's own name-adoption note.
CERTIDAO_ELE_ELA = (
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
    "alteracao): ELE: continuou a usar o mesmo nome. ELA: passou a usar "
    "o nome de PATRICIA ARAUJO PEREIRA COSTA.\n"
)


class TestEleElaAdoptionOverlay:
    def test_the_bride_who_changed_names_gets_the_married_name_and_the_maiden_one_survives(
        self,
    ) -> None:
        ricardo, patricia = find_conjuges(CERTIDAO_ELE_ELA)
        assert patricia.nome == "PATRICIA ARAUJO PEREIRA COSTA"
        assert patricia.nome_anterior == "PATRICIA ARAUJO PEREIRA"
        assert ricardo.nome == "RICARDO MOURA SILVA"
        assert ricardo.nome_anterior is None

    def test_the_groom_can_be_the_one_who_changes_names(self) -> None:
        texto = (
            "CERTIDAO DE CASAMENTO\n"
            "ELE: RICARDO MOURA SILVA, nascido no dia dez de janeiro de mil "
            "novecentos e oitenta, filho de PEDRO MOURA SILVA e de ANA "
            "MOURA SILVA.\n"
            "ELA: PATRICIA ARAUJO PEREIRA, nascida no dia vinte de "
            "fevereiro de mil novecentos e oitenta e dois, filha de JOSE "
            "ARAUJO PEREIRA e de ROSA ARAUJO PEREIRA.\n"
            "Data da celebracao do casamento: 05/06/2010\n"
            "Regime de bens: comunhao parcial de bens\n"
            "Nome que cada um dos conjuges passou a utilizar (quando "
            "houver alteracao): ELE: passou a usar o nome de RICARDO "
            "MOURA PEREIRA. ELA: continuou a usar o mesmo nome.\n"
        )
        ricardo, patricia = find_conjuges(texto)
        assert ricardo.nome == "RICARDO MOURA PEREIRA"
        assert ricardo.nome_anterior == "RICARDO MOURA SILVA"
        assert patricia.nome == "PATRICIA ARAUJO PEREIRA"
        assert patricia.nome_anterior is None

    def test_no_change_on_either_side_leaves_both_qualification_names_untouched(
        self,
    ) -> None:
        texto = (
            "CERTIDAO DE CASAMENTO\n"
            "ELE: RICARDO MOURA SILVA, nascido no dia dez de janeiro de mil "
            "novecentos e oitenta, filho de PEDRO MOURA SILVA e de ANA "
            "MOURA SILVA.\n"
            "ELA: PATRICIA ARAUJO PEREIRA, nascida no dia vinte de "
            "fevereiro de mil novecentos e oitenta e dois, filha de JOSE "
            "ARAUJO PEREIRA e de ROSA ARAUJO PEREIRA.\n"
            "Data da celebracao do casamento: 05/06/2010\n"
            "Regime de bens: comunhao parcial de bens\n"
            "Nome que cada um dos conjuges passou a utilizar (quando "
            "houver alteracao): ELE: continuou a usar o mesmo nome. "
            "ELA: continuou a usar o mesmo nome.\n"
        )
        ricardo, patricia = find_conjuges(texto)
        assert ricardo.nome == "RICARDO MOURA SILVA"
        assert ricardo.nome_anterior is None
        assert patricia.nome == "PATRICIA ARAUJO PEREIRA"
        assert patricia.nome_anterior is None

    def test_no_adoption_clause_at_all_is_a_no_op(self) -> None:
        """A document with only the qualification `ELE:`/`ELA:` pair (no
        later "PASSOU A UTILIZAR" section at all) must behave exactly as
        before this overlay existed."""
        texto = (
            "CERTIDAO DE CASAMENTO\n"
            "ELE: RICARDO MOURA SILVA, nascido no dia dez de janeiro de mil "
            "novecentos e oitenta, filho de PEDRO MOURA SILVA e de ANA "
            "MOURA SILVA.\n"
            "ELA: PATRICIA ARAUJO PEREIRA, nascida no dia vinte de "
            "fevereiro de mil novecentos e oitenta e dois, filha de JOSE "
            "ARAUJO PEREIRA e de ROSA ARAUJO PEREIRA.\n"
            "Data da celebracao do casamento: 05/06/2010\n"
            "Regime de bens: comunhao parcial de bens\n"
        )
        ricardo, patricia = find_conjuges(texto)
        assert ricardo.nome == "RICARDO MOURA SILVA"
        assert patricia.nome == "PATRICIA ARAUJO PEREIRA"
        assert ricardo.nome_anterior is None
        assert patricia.nome_anterior is None


class TestUnrelatedAdoptionLanguageElsewhereIsNeverAttributedToASpouse:
    """The regex-precedence bug (see module docstring, item 2): a stray
    `CONTINUOU A ASSINAR ...` on a WITNESS's own paragraph must never be
    read as either spouse's own married name, even though it sits well
    past both `ELE:`/`ELA:` qualification clauses."""

    def test_a_witnesss_own_name_change_is_not_attributed_to_the_bride(
        self,
    ) -> None:
        texto = (
            "CERTIDAO DE CASAMENTO\n"
            "ELE: ANTONIO CARLOS MENDES, nascido no dia dez de janeiro de "
            "mil novecentos e setenta, filho de PEDRO MENDES e de ROSA "
            "MENDES.\n"
            "ELA: FERNANDA LUCIA ROCHA, nascida no dia vinte de fevereiro "
            "de mil novecentos e setenta e dois, filha de JOAO ROCHA e de "
            "MARIA ROCHA.\n"
            "Data da celebracao do casamento: 05/06/2000\n"
            "Regime de bens: comunhao parcial de bens\n"
            "TESTEMUNHA HELENA DE SOUZA BARROS, QUE, AO CASAR-SE "
            "ANTERIORMENTE, CONTINUOU A ASSINAR HELENA MOREIRA BARROS, "
            "DECLAROU CONHECER OS NUBENTES.\n"
        )
        antonio, fernanda = find_conjuges(texto)
        assert antonio.nome == "ANTONIO CARLOS MENDES"
        assert antonio.nome_anterior is None
        assert fernanda.nome == "FERNANDA LUCIA ROCHA"
        assert fernanda.nome_anterior is None

    def test_ele_regex_itself_requires_the_ele_label_on_the_continuou_branch(
        self,
    ) -> None:
        """Isolates the regex directly: before the `(?:...)` fix, the
        `CONTINUA`/`CONTINUOU` branch matched with NO `ELE:` prefix at
        all — this must now fail."""
        texto_sem_rotulo = "CONTINUOU A ASSINAR HELENA MOREIRA BARROS."
        assert _ADOCAO_ELE_RE.search(texto_sem_rotulo) is None
        assert _ADOCAO_ELA_RE.search(texto_sem_rotulo) is None
