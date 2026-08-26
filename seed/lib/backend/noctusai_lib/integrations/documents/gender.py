"""Read the holder's sex/gender off a Brazilian identity document.

Third sibling of `birthdate.py` and `name.py`, and the same shape on purpose:
pure, label-anchored, import-free of the rest of the package, returning
`(value, confidence, matched_label)` with confidence as a plain string.

🔴 WHY THIS FIELD IS *EASIER* TO READ THAN THE OTHERS, AND WHY THAT IS A TRAP
-----------------------------------------------------------------------------
A birthdate is eight digits that OCR routinely mangles; a name is free text. A
sex field is one character from a two-element alphabet, so the naive reading is
"just find M or F" — and that is exactly the failure mode.

A single letter appears everywhere on an RG: in the issuing state (`SP`), in
`FILIACAO`, in a middle initial, in `DOC. ORIGEM`, in the word `MASC` inside
some other word. A bare letter scan would return a confident answer on almost
any document and be wrong on many. So an unlabelled single letter is NEVER
accepted here — unlike `birthdate`, which does allow a lone plausible date as a
low-confidence guess, because a well-formed date is itself strong evidence.

The rule is therefore: the value must sit next to a sex label, or it does not
exist. A full word (`MASCULINO`) is accepted unlabelled at LOW confidence,
because that word has no other reason to be on the document.

WHY IT NORMALISES TO WORDS
--------------------------
The consuming column holds "Masculino" / "Feminino" verbatim — it is what the
UI's dropdown offers and what an operator would have typed. Returning `"M"`
would mean every reader decoding it, and the first reader that forgot would
store a letter where the rest of the product expects a word.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

MASCULINO = "Masculino"
FEMININO = "Feminino"

#: How far back from a value to look for its label. Matches `birthdate`'s
#: window — the layouts are the same documents.
_LABEL_WINDOW = 48

#: Labels that genuinely introduce the holder's sex. `SEXO` is what the RG and
#: the CNH both print.
_SEX_LABELS = (
    "SEXO",
    "GENERO",
    "SEX",
)

#: Labels that introduce SOMEBODY ELSE's sex, or something that is not a sex at
#: all but sits next to a lone letter. Same decoy discipline `birthdate` uses
#: for `DATA DE EMISSAO` — the field exists, it is simply not ours.
#:
#: `FILIACAO` is the important one: a parent's name block is where a stray
#: initial is most likely to be found, and attributing a parent's anything to
#: the holder is the error this whole module family is built to avoid.
_DECOY_LABELS = (
    "FILIACAO",
    "PAI",
    "MAE",
    "CONJUGE",
    "NOME DA MAE",
    "NOME DO PAI",
)

#: Whole words, which are unambiguous wherever they appear.
_PALAVRAS = {
    "MASCULINO": MASCULINO,
    "MASC": MASCULINO,
    "HOMEM": MASCULINO,
    "FEMININO": FEMININO,
    "FEM": FEMININO,
    "MULHER": FEMININO,
}

#: Single letters, accepted ONLY immediately after a sex label.
_LETRAS = {"M": MASCULINO, "F": FEMININO}

_PALAVRA_RE = re.compile(
    r"\b(" + "|".join(sorted(_PALAVRAS, key=len, reverse=True)) + r")\b"
)
_LETRA_RE = re.compile(r"\b([MF])\b")


def normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed.

    Same normalisation the sibling parsers apply, for the same reason: an OCR
    pass over a photographed card produces `SÉXO` and `Masculino` in equal
    measure, and matching against every casing/accent variant is a losing game.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper())


def _label_before(haystack: str, at: int) -> tuple[Optional[str], bool]:
    """The nearest sex label preceding `at`, and whether it is a decoy.

    Returns `(label, is_decoy)`. A decoy wins over a real label when it is
    closer, because proximity is what actually binds a value to a field on
    these layouts.
    """
    window = haystack[max(0, at - _LABEL_WINDOW) : at]
    melhor: Optional[str] = None
    melhor_pos = -1
    decoy = False
    for rotulo in _SEX_LABELS + _DECOY_LABELS:
        pos = window.rfind(rotulo)
        if pos > melhor_pos:
            melhor_pos = pos
            melhor = rotulo
            decoy = rotulo in _DECOY_LABELS
    if melhor is None or melhor_pos < 0:
        return (None, False)
    return (melhor, decoy)


def find_gender(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """Extract the holder's sex.

    Returns `(value, confidence, matched_label)`, confidence being one of
    `"alta"` / `"baixa"` / `"nenhuma"` — the string values of
    `types.ExtractionConfidence`, kept as plain strings so this module stays
    import-free of the rest of the package.

    - **alta** — found next to a sex label, and every labelled reading agrees.
    - **baixa** — a whole word (`MASCULINO`) with no label. Unambiguous as a
      token, but unanchored, so a human confirms.
    - **nenhuma** — nothing, or readings that disagree. 🔴 Disagreement is
      reported as ABSENCE, never resolved by preferring one: two different sex
      values on one document means the layout was misread, and picking a winner
      would write a coin-flip onto a person's record.
    """
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma", None)

    rotulados: list[tuple[str, str]] = []
    soltos: list[str] = []

    # Whole words — valid anywhere, better when labelled.
    for m in _PALAVRA_RE.finditer(norm):
        valor = _PALAVRAS[m.group(1)]
        rotulo, decoy = _label_before(norm, m.start())
        if decoy:
            continue
        if rotulo:
            rotulados.append((valor, rotulo))
        else:
            soltos.append(valor)

    # Bare letters — ONLY when a sex label introduces them. See the module
    # docstring: an unlabelled `M` is far more likely to be a state code or an
    # initial than the holder's sex.
    for m in _LETRA_RE.finditer(norm):
        rotulo, decoy = _label_before(norm, m.start())
        if decoy or not rotulo:
            continue
        rotulados.append((_LETRAS[m.group(1)], rotulo))

    if rotulados:
        distintos = {v for v, _ in rotulados}
        if len(distintos) == 1:
            valor, rotulo = rotulados[0]
            return (valor, "alta", rotulo)
        return (None, "nenhuma", None)

    if soltos:
        distintos = set(soltos)
        if len(distintos) == 1:
            return (soltos[0], "baixa", None)

    return (None, "nenhuma", None)


__all__ = ["FEMININO", "MASCULINO", "find_gender", "normalize"]
