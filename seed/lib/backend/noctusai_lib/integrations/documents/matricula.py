"""Read the número de matrícula off a Brazilian certidão de matrícula.

Fourth sibling of `birthdate.py`, `name.py` and `gender.py`, same contract:
pure, label-anchored, import-free of the rest of the package, returning
`(value, confidence, matched_label)` with confidence as a plain string.

🔴 WHY THIS IS HARDER THAN IT LOOKS
------------------------------------
A matrícula is wall-to-wall numbers. The first page alone carries the
matrícula number, a livro number, a folha number, a CNM/CNS code, an IPTU
inscription, a CEP, a CPF or two, several dates, an área in m², and a protocol
number — most of them 4–8 digits, i.e. indistinguishable from the answer by
shape alone.

So "find the longest number" and "find the first number" are both wrong, and
wrong in the worst way: they return something plausible on every document. The
only reliable signal is the LABEL, and this parser accepts nothing without one.

There is no low-confidence fallback for an unlabelled number, unlike
`birthdate` (where a well-formed date is itself evidence). An unlabelled
integer on a matrícula is evidence of nothing.

🔴 AND WHY THE FIRST PAGE MATTERS
---------------------------------
A matrícula's body TEXT cites other matrículas constantly — "originada da
matrícula 12.345", "conforme matrícula nº 9.876 deste registro". Those are real
labelled matches for a DIFFERENT property. Taking "the first labelled match"
would usually be right and occasionally attach a neighbour's registry number to
this sale, which is the kind of error nobody catches until a cartório rejects
the paperwork.

The rule that survives this: the document's OWN number is the one in the
heading, before the body starts. So matches are scored by how early they
appear, and a match that arrives after a body-opening marker is discarded
outright.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

#: How far back from a number to look for its label.
_LABEL_WINDOW = 40

#: Labels that introduce THIS document's matrícula number.
_MATRICULA_LABELS = (
    "MATRICULA N",
    "MATRICULA NO",
    "MATRICULA NUMERO",
    "MATRICULA",
    "MAT.",
)

#: Labels that introduce a DIFFERENT number that sits in the same visual block.
#: Livro/folha are the dangerous ones: on most layouts they are printed inches
#: from the matrícula number, in the same typeface, on the same line.
_DECOY_LABELS = (
    "LIVRO",
    "FOLHA",
    "FLS",
    "FICHA",
    "PROTOCOLO",
    "CNM",
    "CNS",
    "INSCRICAO",
    "IPTU",
    "CONTRIBUINTE",
    "CEP",
    "CPF",
    "CNPJ",
    "PROCESSO",
    "AREA",
)

#: Text that means the heading is over and the narrative has begun. Everything
#: after the FIRST of these is body, and every matrícula number in the body
#: belongs to some other property.
_BODY_MARKERS = (
    "ORIGINADA DA",
    "ORIUNDA DA",
    "PROVENIENTE DA",
    "AV.1",
    "AV-1",
    "AVERBACAO",
    "R.1",
    "R-1",
    "REGISTRO ANTERIOR",
    "PROPRIETARIO",
)

#: 3–12 digits, optionally dotted as thousands. Deliberately NOT anchored to a
#: fixed width: matrícula numbering is per-cartório and ranges from three
#: digits in small comarcas to eight or more in São Paulo.
_NUMERO = re.compile(r"\b(\d{1,3}(?:\.\d{3})+|\d{3,12})\b")


def normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper())


def _limpar(numero: str) -> str:
    """Drop thousands dots. `12.345` and `12345` are the same matrícula, and
    storing both spellings would make the column fail to match itself."""
    return numero.replace(".", "")


def _corpo_comeca_em(texto: str) -> int:
    """Offset of the first body marker, or len(texto) if the heading is all
    there is (a short certidão, or a transcription that lost its structure)."""
    posicoes = [texto.find(m) for m in _BODY_MARKERS]
    reais = [p for p in posicoes if p >= 0]
    return min(reais) if reais else len(texto)


def _label_before(haystack: str, at: int) -> tuple[Optional[str], bool]:
    """Nearest label preceding `at`, and whether it is a decoy.

    Proximity decides: on these layouts a number belongs to whichever label sits
    closest to its left, and a decoy that is nearer than a real label means the
    number is the decoy's.
    """
    window = haystack[max(0, at - _LABEL_WINDOW) : at]
    melhor: Optional[str] = None
    melhor_pos = -1
    decoy = False
    for rotulo in _MATRICULA_LABELS + _DECOY_LABELS:
        pos = window.rfind(rotulo)
        # `>=` so that on a tie the LONGER, more specific label wins —
        # "MATRICULA N" must beat the "MATRICULA" prefix inside it.
        if pos > melhor_pos or (pos == melhor_pos and pos >= 0 and melhor and len(rotulo) > len(melhor)):
            melhor_pos = pos
            melhor = rotulo
            decoy = rotulo in _DECOY_LABELS
    if melhor is None or melhor_pos < 0:
        return (None, False)
    return (melhor, decoy)


def find_matricula(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """Extract this document's própria matrícula number.

    Returns `(value, confidence, matched_label)`, confidence being one of
    `"alta"` / `"baixa"` / `"nenhuma"` — the string values of
    `types.ExtractionConfidence`, kept as plain strings so this module stays
    import-free of the rest of the package.

    - **alta** — label-anchored, in the heading, and every heading match agrees.
    - **baixa** — label-anchored but only found in the BODY, i.e. the heading
      did not survive transcription. Plausible and worth offering, not worth
      writing unattended.
    - **nenhuma** — no labelled number, or heading matches that disagree.
      🔴 Disagreement is absence: two different numbers both labelled
      "matrícula" in the heading means the layout was misread, and choosing one
      would attach a registry number to a property at random.
    """
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma", None)

    fim_do_cabecalho = _corpo_comeca_em(norm)
    cabecalho: list[tuple[str, str]] = []
    corpo: list[tuple[str, str]] = []

    for m in _NUMERO.finditer(norm):
        rotulo, decoy = _label_before(norm, m.start())
        if decoy or not rotulo:
            continue
        valor = _limpar(m.group(1))
        if m.start() < fim_do_cabecalho:
            cabecalho.append((valor, rotulo))
        else:
            corpo.append((valor, rotulo))

    if cabecalho:
        distintos = {v for v, _ in cabecalho}
        if len(distintos) == 1:
            valor, rotulo = cabecalho[0]
            return (valor, "alta", rotulo)
        return (None, "nenhuma", None)

    if corpo:
        # The heading did not survive. The EARLIEST labelled number is the best
        # remaining guess, and it is offered as a guess.
        valor, rotulo = corpo[0]
        return (valor, "baixa", rotulo)

    return (None, "nenhuma", None)


__all__ = ["find_matricula", "normalize"]
