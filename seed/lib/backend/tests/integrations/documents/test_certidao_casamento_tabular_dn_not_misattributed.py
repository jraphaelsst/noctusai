"""🔴 THE BUG THIS FILE CLOSES — real, measured (P1/883, 2026-09-28)

A tabular, one-field-per-row certidão layout names two co-equal nubentes
(`NOMES` / interleaved CPF rows) and THEN lists each person's own facts —
`DATA DE NASCIMENTO`, `NACIONALIDADE`, ... — as separate labelled rows,
never the narrative "NOME, nascido no dia ..." clause
`conjuges.find_conjuges`'s segment-scoping already understands. On that
layout its per-person `data_nascimento` stays unset for BOTH spouses.

Before this fix, `real.LadderIdentityExtractor._ler` fell back to the
WHOLE-DOCUMENT `birthdate.find_birthdate` reading whenever the titular's
OWN segment came up empty — a reading with no notion of WHICH of the two
co-equal holders it belongs to. When one spouse's own `DATA DE NASCIMENTO`
value happens to sit closer to its label than the other's (an ordinary
layout asymmetry, not a misread), that reading survives as the document's
one "alta"-confidence candidate — and could silently become the WRONG
spouse's date, worse than reporting nothing.

Once a titular is resolved among two co-equal holders, only THEIR OWN
segment-scoped reading may answer `data_nascimento` — never the unscoped
whole-document guess. Invented names below; the shape (not the values)
mirrors the real 883 certidão.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.types import TextSource, TitularEsperado


class _Ladder:
    """DI stand-in for `DocumentTextLadder` — text-layer rung only."""

    def __init__(self, texto: str) -> None:
        self.texto = texto

    async def to_text(self, content, mimetype=None, filename=None, *, pular_camada_texto=False):
        return (self.texto, TextSource.TEXT_LAYER, None)


#: Person A's own `DATA DE NASCIMENTO` sits far from its value (two filler
#: rows between them — an ordinary certidão layout, not noise) — far enough
#: that `birthdate._LABEL_WINDOW` (48 chars) never reaches it, so the
#: whole-document scan sees it as UNLABELLED. Person B's sits right next to
#: its own label instead, so the whole-document scan sees THAT one as
#: `"alta"` — an asymmetry that is nobody's mistake, just the layout.
CERTIDAO_TABULAR = """
NOMES

FULANO DE TAL SANTOS

NUMERO DO CPF
111.222.333-44

CICLANA DE TAL PEREIRA

NUMERO DO CPF
555.666.777-88

MATRICULA
115568 01 55 2011 2 00198

DATA DE NASCIMENTO
NATURALIDADE MUNICIPIO DE SAO PAULO ESTADO DE SAO PAULO
ESTADO CIVIL SOLTEIRO ANTES DO CASAMENTO ATUAL
04 10 1961

NACIONALIDADE
BRASILEIRA

DATA DE NASCIMENTO
20 04 1990

NACIONALIDADE
BRASILEIRA

DATA DO CASAMENTO
DIA MES ANO
15 08 2010

REGIME DE BENS
COMUNHAO PARCIAL DE BENS
"""


class TestTabularLayoutDoesNotMisattributeTheOtherSpousesBirthdate:
    @pytest.mark.asyncio
    async def test_the_titular_whose_own_row_is_far_from_its_label_gets_no_dn_not_the_others(
        self,
    ) -> None:
        # Sanity check on the fixture itself: the whole-document scan DOES
        # confidently find a (real, but WRONG-for-this-titular) date — this
        # is the exact shape that used to leak through.
        from noctusai_lib.integrations.documents.birthdate import find_birthdate

        whole_doc = find_birthdate(CERTIDAO_TABULAR)
        assert whole_doc[0] is not None and whole_doc[1] == "alta", (
            "fixture no longer reproduces the asymmetric-label-distance shape"
        )

        out = await LadderIdentityExtractor(ladder=_Ladder(CERTIDAO_TABULAR)).extract(
            b"%PDF",
            mimetype="application/pdf",
            titular=TitularEsperado(nome="Fulano de Tal Santos"),
        )
        assert out.nome == "FULANO DE TAL SANTOS"
        # Never the whole-document reading (which belongs to the OTHER spouse
        # on this fixture): the titular's OWN row, attributed by the tabular
        # branch of `conjuges.find_conjuges` (2026-09-28 follow-up).
        assert out.data_nascimento is not None
        assert out.data_nascimento != whole_doc[0]
        assert out.data_nascimento.isoformat() == "1961-10-04"
        assert out.data_nascimento_confianca.value != "alta"

    @pytest.mark.asyncio
    async def test_the_other_titular_is_not_credited_by_coincidence_either(self) -> None:
        """The spouse whose row DOES sit near a label is credited only via
        the segment scope that attributes it to HER — never a coincidental
        whole-document match, whose confidence (`alta`) it must not inherit."""
        out = await LadderIdentityExtractor(ladder=_Ladder(CERTIDAO_TABULAR)).extract(
            b"%PDF",
            mimetype="application/pdf",
            titular=TitularEsperado(nome="Ciclana de Tal Pereira"),
        )
        assert out.nome == "CICLANA DE TAL PEREIRA"
        # Credited through HER OWN row's positional attribution, capped below
        # `alta` — not through the whole-document coincidence.
        assert out.data_nascimento is not None
        assert out.data_nascimento.isoformat() == "1990-04-20"
        assert out.data_nascimento_confianca.value == "media"

    @pytest.mark.asyncio
    async def test_couple_level_facts_are_unaffected(self) -> None:
        """The fix is scoped to `data_nascimento` alone — the couple-level
        facts on the same result still come through normally."""
        out = await LadderIdentityExtractor(ladder=_Ladder(CERTIDAO_TABULAR)).extract(
            b"%PDF",
            mimetype="application/pdf",
            titular=TitularEsperado(nome="Fulano de Tal Santos"),
        )
        assert out.regime_bens == "comunhao_parcial"


# --- `conjuges.find_conjuges` tabular branch (follow-up, 2026-09-28) --------

from noctusai_lib.integrations.documents.conjuges import find_conjuges  # noqa: E402

#: Same layout, fields interleaved BY FIELD (A's DN, B's DN, A's nac, B's nac)
#: instead of grouped by person — the positional split must hold either way.
CERTIDAO_TABULAR_POR_CAMPO = """
NOMES

FULANO DE TAL SANTOS

NUMERO DO CPF
111.222.333-44

CICLANA DE TAL PEREIRA

NUMERO DO CPF
555.666.777-88

DATA DE NASCIMENTO
04 10 1961

DATA DE NASCIMENTO
20 04 1990

PROFISSAO
ENGENHEIRO

PROFISSAO
ADVOGADA

DATA DO CASAMENTO
DIA MES ANO
15 08 2010
"""


class TestFindConjugesTabularBranch:
    def test_grouped_by_person_each_spouse_gets_their_own_row(self) -> None:
        a, b = find_conjuges(CERTIDAO_TABULAR)
        assert (a.nome, a.data_nascimento.isoformat()) == ("FULANO DE TAL SANTOS", "1961-10-04")
        assert (b.nome, b.data_nascimento.isoformat()) == ("CICLANA DE TAL PEREIRA", "1990-04-20")
        assert a.nacionalidade and b.nacionalidade

    def test_interleaved_by_field_each_spouse_gets_their_own_row(self) -> None:
        a, b = find_conjuges(CERTIDAO_TABULAR_POR_CAMPO)
        assert a.data_nascimento.isoformat() == "1961-10-04"
        assert b.data_nascimento.isoformat() == "1990-04-20"
        assert a.profissao and "ENGENHEIR" in a.profissao.upper()
        assert b.profissao and "ADVOGAD" in b.profissao.upper()

    def test_positional_attribution_is_never_alta(self) -> None:
        for c in find_conjuges(CERTIDAO_TABULAR_POR_CAMPO):
            assert c.data_nascimento_confianca in ("baixa", "media")
            assert c.profissao_confianca in ("baixa", "media")

    def test_the_last_spouses_empty_row_never_reads_the_wedding_date(self) -> None:
        """B's own DN row is blank: the couple's `DATA DO CASAMENTO` row
        closes B's segment, so B gets nothing — not the wedding date."""
        texto = CERTIDAO_TABULAR_POR_CAMPO.replace("DATA DE NASCIMENTO\n20 04 1990\n", "DATA DE NASCIMENTO\n\n")
        a, b = find_conjuges(texto)
        assert a.data_nascimento.isoformat() == "1961-10-04"
        assert b.data_nascimento is None

    def test_a_label_count_other_than_two_is_ambiguous_and_reads_nothing(self) -> None:
        texto = CERTIDAO_TABULAR_POR_CAMPO.replace(
            "PROFISSAO\nENGENHEIRO\n", "PROFISSAO\nENGENHEIRO\n\nPROFISSAO\nMEDICO\n"
        )
        a, b = find_conjuges(texto)
        assert a.profissao is None and b.profissao is None
        # Other fields, still exactly two rows each, are unaffected.
        assert a.data_nascimento.isoformat() == "1961-10-04"
