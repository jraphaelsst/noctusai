"""The generator's money-in-words style — ONE place, shared by text and lint.

Owner decision 2026-10-05 (counts over the signed/draft contract corpus):
number-in-words groups carry NO commas — "dois milhões novecentos e sessenta
mil reais" (signed 62 vs 9; "mil," 801 vs 42). The seed's
`noctusai_lib.domain.texto_ptbr` keeps the comma by default (other consumers'
output unchanged); this module passes the named seam `virgulas=False` so the
rendered text (`contexto`, `frases`) and the post-render lint
(`EXTENSO_DIVERGENTE`) can never disagree about it.
"""
from __future__ import annotations

from decimal import Decimal

from noctusai_lib.domain import texto_ptbr


def reais_por_extenso(valor: Decimal) -> str:
    return texto_ptbr.reais_por_extenso(valor, virgulas=False)


def brl_por_extenso(valor: Decimal) -> str:
    return texto_ptbr.brl_por_extenso(valor, virgulas=False)


__all__ = ["brl_por_extenso", "reais_por_extenso"]
