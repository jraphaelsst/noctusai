"""`find_nacionalidade` — the holder's nationality off a Brazilian identity
document or certidão.

🔴 WHAT THESE TESTS ARE REALLY FOR
------------------------------------
The one case this module exists to get right that no other sibling faces:
canonicalising ACROSS grammatical gender before checking two labelled
readings for agreement — a certidão de casamento names both spouses' own
nationality, each spelled in that person's own gender ("brasileiro" /
"brasileira"), and the naive "compare the raw strings" rule would report
that as a disagreement on the single most common document this module
reads. Most of what follows exercises that, plus the family's usual
"never guess unlabelled" and "FILIAÇÃO is not the holder's" rules.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents import find_nacionalidade
from noctusai_lib.integrations.documents.nacionalidade import (
    NACIONALIDADE_VALORES,
    canonico,
    feminino,
)


class TestLabelled:
    def test_the_new_model_cnh_layout(self):
        """"NACIONALIDADE\\nBRASILEIRO" — the exact CNH layout this module
        was built to close (`NOC-REMEDIATE[nacionalidade-identity-parser]`)."""
        valor, conf, rotulo = find_nacionalidade("NACIONALIDADE\nBRASILEIRO")
        assert (valor, conf) == ("brasileiro", "alta")
        assert rotulo == "NACIONALIDADE"

    def test_de_nacionalidade_brasileira(self):
        valor, conf, rotulo = find_nacionalidade(
            "ALMIR TEIXEIRA DA COSTA, de nacionalidade brasileira, filho de..."
        )
        assert (valor, conf) == ("brasileiro", "alta")
        assert rotulo == "DE NACIONALIDADE"

    def test_a_non_brazilian_gentilico(self):
        valor, conf, _ = find_nacionalidade("NACIONALIDADE: ITALIANA")
        assert (valor, conf) == ("italiano", "alta")

    def test_accents_and_casing_do_not_matter(self):
        valor, conf, _ = find_nacionalidade("Nacionalidade: Português")
        assert (valor, conf) == ("português", "alta")

    def test_the_hyphenated_gentilico(self):
        valor, _, _ = find_nacionalidade("NACIONALIDADE NORTE-AMERICANA")
        assert valor == "norte-americano"


class TestNeverGuessed:
    def test_an_unlabelled_gentilico_is_not_accepted(self):
        """Unlike `gender.py`'s MASCULINO/FEMININO, a gentílico has every
        reason to appear loose in ordinary legal prose — accepting it
        unlabelled would be a guess wearing a confidence score."""
        valor, conf, _ = find_nacionalidade(
            "sociedade brasileira registrada nos termos da legislação brasileira"
        )
        assert valor is None
        assert conf == "nenhuma"

    def test_a_document_without_the_field_is_not_an_error(self):
        valor, conf, _ = find_nacionalidade("CPF 123.456.789-00\nNOME FULANO DE TAL")
        assert valor is None
        assert conf == "nenhuma"

    def test_empty_text(self):
        assert find_nacionalidade("") == (None, "nenhuma", None)


class TestFiliacaoIsNotTheHolders:
    def test_a_parents_block_does_not_supply_the_holders_nationality(self):
        valor, conf, _ = find_nacionalidade(
            "FILIACAO PEDRO TEIXEIRA DA COSTA NACIONALIDADE BRASILEIRO"
        )
        assert valor is None
        assert conf == "nenhuma"


class TestGrammaticalGenderIsNotDisagreement:
    def test_two_spouses_of_the_same_nationality_agree(self):
        """The certidão de casamento fixture this module exists for: two
        people, two grammatical genders, ONE nationality. Compared as raw
        strings ("brasileiro" vs "brasileira") this would misread as a
        disagreement; canonicalised, it correctly resolves at `alta`."""
        texto = (
            "ALMIR TEIXEIRA DA COSTA, nascido em Duque de Caxias, RJ, "
            "de nacionalidade brasileira, filho de PEDRO TEIXEIRA DA COSTA "
            "e de MARIA JACIRA MENDES DA COSTA. "
            "MARIANA PELLEGRINI RANGEL, nascida no Subdistrito Aclimação, "
            "São Paulo, SP, de nacionalidade brasileira, filha de EMILIO "
            "RANGEL e de ANGELINA NUNES RANGEL."
        )
        valor, conf, _ = find_nacionalidade(texto)
        assert (valor, conf) == ("brasileiro", "alta")

    def test_two_genuinely_different_nationalities_disagree(self):
        """A real binational couple is not swallowed by the canonicalisation
        above — it still, correctly, cannot be resolved here."""
        texto = (
            "ALMIR TEIXEIRA DA COSTA, de nacionalidade brasileira, filho de... "
            "MARIANA PELLEGRINI RANGEL, de nacionalidade italiana, filha de..."
        )
        valor, conf, _ = find_nacionalidade(texto)
        assert valor is None
        assert conf == "nenhuma"


class TestCanonico:
    def test_either_grammatical_gender_resolves_to_the_masculine_canonical(self):
        assert canonico("italiana") == "italiano"
        assert canonico("ITALIANO") == "italiano"

    def test_the_legacy_parenthetical_form_is_not_matched(self):
        """`"Brasileiro(a)"` is a legacy free-text form the product's own
        generator already special-cased before this module existed
        (`contrato_gerador/frases.py::_NACIONALIDADE_BR`) — this function
        does not need to also understand it; free text that misses the
        vocabulary passes through untouched at the CALLER, not here."""
        assert canonico("Brasileiro(a)") is None

    def test_unknown_free_text_returns_none(self):
        assert canonico("xyz") is None
        assert canonico("") is None
        assert canonico(None) is None  # type: ignore[arg-type]


class TestFeminino:
    def test_every_canonical_value_has_a_feminine_form(self):
        for valor in NACIONALIDADE_VALORES:
            assert feminino(valor), f"missing feminine form for {valor!r}"

    def test_an_unknown_value_returns_none(self):
        assert feminino("xyz") is None


class TestPluralGentilicos:
    """2026-09-23, real, measured: `\\bBRASILEIR[OA]\\b` never matched the
    PLURAL at all — `\\b` cannot fire between two word characters (`O` then
    `S`), so a certidão's "ambos... brasileiros" phrasing silently read as
    `nenhuma`. Every gentílico now accepts its plural, canonicalising to
    the SAME singular masculine token."""

    @pytest.mark.parametrize(
        "bruto,esperado",
        [
            ("BRASILEIROS", "brasileiro"),
            ("BRASILEIRAS", "brasileiro"),
            ("PORTUGUESES", "português"),  # irregular masc plural (+ES)
            ("PORTUGUESAS", "português"),
            ("ITALIANOS", "italiano"),
            ("ESPANHOIS", "espanhol"),  # irregular masc plural (-OL -> -OIS)
            ("ESPANHOLAS", "espanhol"),
            ("ALEMAES", "alemão"),  # irregular masc plural (-AO -> -AES)
            ("ALEMAS", "alemão"),
            ("JAPONESES", "japonês"),
            ("CHINESES", "chinês"),
            ("FRANCESES", "francês"),
            ("LIBANESES", "libanês"),
            ("URUGUAIOS", "uruguaio"),
        ],
    )
    def test_plural_canonicalises_to_the_singular_masculine(self, bruto, esperado):
        assert canonico(bruto) == esperado

    def test_a_certidao_style_collective_plural_is_found_labelled(self):
        texto = "NACIONALIDADE: brasileiros"
        valor, confianca, _ = find_nacionalidade(texto)
        assert valor == "brasileiro"
        assert confianca == "alta"

    def test_brasileira_nata_still_resolves_the_gentilico_alone(self):
        # "nata"/"nato" (natural-born) is a trailing qualifier, not part of
        # the gentílico itself — the word-boundary match on "BRASILEIRA"
        # is unaffected by what follows it.
        texto = "de NACIONALIDADE brasileira nata"
        valor, confianca, _ = find_nacionalidade(texto)
        assert valor == "brasileiro"
        assert confianca == "alta"
