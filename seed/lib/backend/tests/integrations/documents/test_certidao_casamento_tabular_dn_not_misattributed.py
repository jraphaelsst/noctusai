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
        # Missing, never the whole-document reading (which belongs to the
        # OTHER spouse on this fixture) — honesty over a guessed coverage win.
        assert out.data_nascimento is None
        assert out.data_nascimento_confianca.value == "nenhuma"

    @pytest.mark.asyncio
    async def test_the_other_titular_is_not_credited_by_coincidence_either(self) -> None:
        """The spouse whose row DOES sit near a label must not be credited
        with it either, unless it is genuinely attributed to THEM by the
        segment scope — a coincidental match is still a guess."""
        out = await LadderIdentityExtractor(ladder=_Ladder(CERTIDAO_TABULAR)).extract(
            b"%PDF",
            mimetype="application/pdf",
            titular=TitularEsperado(nome="Ciclana de Tal Pereira"),
        )
        assert out.nome == "CICLANA DE TAL PEREIRA"
        assert out.data_nascimento is None

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
