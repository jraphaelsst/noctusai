"""Money — pure, shared: read a monetary field off one already-label-matched
value string, and cross-check it against its own printed "valor por
extenso" using the seed's own `texto_ptbr` (`parse_brl` / `reais_por_extenso`)
rather than a second, bespoke money parser.

THE MONEY ANALOGUE OF A CHECK DIGIT
------------------------------------
A CPF carries two check digits — a mod-11 function of the other nine — so a
document that states one can be verified against itself (`cpf.is_valid`). A
Brazilian legal document that prints a money value routinely does the same
thing in words: "R$ 350.000,00 (trezentos e cinquenta mil reais)". Two
independently-printed representations of the SAME number, and a mismatch
between them is exactly the signal a failed CPF check digit is — a
document-authoring inconsistency (or a vision misread of one of the two), not
noise to shrug past.

Shared by `guia_itbi.py` and `financiamento_imobiliario.py` — every one of
the negociação/financiamento documents prints at least one money field
(valor de compra e venda, valor financiado, FGTS, o valor do ITBI...), so
this is `cartao_cnpj.py`'s per-field parsing shape pulled OUT into its own
module before a THIRD copy could appear — N=2 already, inside this very
slice.

WHY THERE IS NO `TextSource` PARAMETER HERE
---------------------------------------------
`ler_valor` never claims `alta` on its own. The ceiling it can reach
(`media`) requires INTERNAL corroboration — the printed extenso agreeing —
never a claim about WHERE the text came from. Whether `media` survives
contact with a vision-sourced document (the contract's rule: capped at
`baixa` regardless, "never alta from vision") is the document extractor's
call, because only IT holds the `TextSource` — the same split
`cartao_cnpj._temper` draws between field-level and source-level confidence,
kept there again here rather than threaded through this module's signature.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from noctusai_lib.domain.texto_ptbr import parse_brl, reais_por_extenso
from noctusai_lib.integrations.documents.types import ExtractionConfidence

#: A `R$`-prefixed (optional) money run — digits, dots and commas — the ONLY
#: shape `parse_brl` accepts once whitespace noise is collapsed out of it.
#: `\d[\d.\s]*` rather than the stricter grouped-thousands shape on purpose:
#: this regex's job is to FIND the run inside a longer string (which may
#: carry a trailing extenso, or a stray label echo); `parse_brl` itself is
#: what actually validates the digits it is handed.
_VALOR_RUN_RE = re.compile(r"(?:R\$)?\s*\d[\d.\s]*,\s*\d{2}", re.IGNORECASE)

#: A trailing parenthetical extenso — "(mil, duzentos ... reais)" — the
#: shape `texto_ptbr.brl_por_extenso` itself prints, and what a document
#: that states its own value in words follows too.
_EXTENSO_RE = re.compile(r"\(([^()]+)\)\s*$")


def _normalizar_valor_bruto(bruto: str) -> str:
    """Collapse OCR/vision whitespace noise INSIDE a money run only — never
    outside it, and never a digit re-guessed. `"R$1. 234,56"` /
    `"1 . 234,56"` become `"R$1.234,56"` / `"1.234,56"`; a string with no
    such run is returned unchanged (and will simply fail to match below,
    same as before this normaliser existed)."""
    normalizado = re.sub(r"(?i)r\s*\$", "R$", bruto or "")

    def _fechar(m: "re.Match[str]") -> str:
        return re.sub(r"\s+", "", m.group(0))

    return _VALOR_RUN_RE.sub(_fechar, normalizado)


def _chave_extenso(txt: str) -> str:
    """Case/accent/whitespace-insensitive comparison key — a document's own
    typography (capitalisation, an extra space, a line-wrap) must never
    register as a disagreement `reais_por_extenso` itself would never
    produce either."""
    decomposed = unicodedata.normalize("NFKD", txt or "")
    sem_acento = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento.strip().lower())


@dataclass(frozen=True)
class ValorLido:
    """One monetary field's reading, plus its own extenso cross-check.

    `confianca` never reaches `ExtractionConfidence.ALTA` here — see the
    module docstring for why that ceiling is the document extractor's call,
    not this one's.
    """

    valor: Optional[Decimal] = None
    #: The printed extenso text, verbatim, when a trailing parenthetical was
    #: present. `None` when the line carried no extenso at all — distinct
    #: from `extenso_confere=False`, which means one WAS present and
    #: disagreed with `valor`.
    extenso: Optional[str] = None
    #: `None` when there was no extenso to check; `True`/`False` once one
    #: was found, comparing it against `texto_ptbr.reais_por_extenso(valor)`.
    extenso_confere: Optional[bool] = None
    confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA


def ler_valor(rotulo_linha: str) -> ValorLido:
    """One already-label-matched value string → `ValorLido`. Pure, never
    raises.

    `rotulo_linha` is the VALUE side of a matched `RÓTULO: valor` line — the
    label itself already stripped by the caller's own box/synonym matcher.
    This module never searches for labels, only parses what it is handed,
    same division of labour `cpf.py`/`cnpj.py` keep from their own callers.
    """
    bruto = rotulo_linha or ""
    m = _VALOR_RUN_RE.search(_normalizar_valor_bruto(bruto))
    if not m:
        return ValorLido()

    try:
        valor = parse_brl(m.group(0))
    except ValueError:
        return ValorLido()

    extenso: Optional[str] = None
    extenso_confere: Optional[bool] = None
    confianca = ExtractionConfidence.BAIXA

    m_extenso = _EXTENSO_RE.search(bruto)
    if m_extenso:
        extenso = m_extenso.group(1).strip()
        try:
            esperado = reais_por_extenso(valor)
        except ValueError:
            esperado = None
        if esperado is not None:
            extenso_confere = _chave_extenso(extenso) == _chave_extenso(esperado)
            if extenso_confere:
                confianca = ExtractionConfidence.MEDIA

    return ValorLido(
        valor=valor,
        extenso=extenso,
        extenso_confere=extenso_confere,
        confianca=confianca,
    )


__all__ = ["ValorLido", "ler_valor"]
