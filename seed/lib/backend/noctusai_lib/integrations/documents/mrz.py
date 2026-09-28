"""ICAO 9303 TD1 machine-readable-zone primitives shared by two field parsers.

Sibling of `labels.py` / `text.py`: a leaf-level helper both `gender.py` and
`name.py` need, kept here instead of being either duplicated in both or
cross-imported between two field-parser modules (which `name.py`'s own
comments on `_CPF_SHAPE_RE` document as deliberately avoided — a field
parser stays import-free of its SIBLING parsers, even when it needs to
recognise a shape or a structural check another one of them already
implements).

WHY THE CHECK DIGIT MATTERS HERE, NOT JUST FOR SEX
---------------------------------------------------
`gender.py` already established the reasoning this module reuses: a TD1
MRZ's line 2 (`YYMMDD C S YYMMDD C NAT ...`) is *structurally anchored* —
the sex letter sits between two dates whose ICAO check digits must both
verify, so an OCR misread of a surrounding digit fails the match instead
of producing a wrong value. That anchor is exactly what `name.py` needs
for a different purpose: TD1's line 3 (the name field) sits immediately
after a GENUINE line 2, and without the check-digit gate there would be no
reliable way to tell "this is really the MRZ block" apart from unrelated
caret-heavy text elsewhere on a scanned page.

THE PRODUCTION BUG THIS EXISTS FOR (real, measured, P2 corpus, 2026-09-28)
---------------------------------------------------------------------------
A CNH-e's vision transcription wrote the holder's name under the WRONG
label — the card prints "1 NOME" right beside "1ª HABILITAÇÃO", and the
model attributed the name to the latter. `name.py`'s label-anchored reader
correctly found nothing under that mislabelling. The same transcription's
MRZ line 3 carries the name too (subject to its own OCR risk — a digit read
in place of a letter — and to ICAO's own 30-character field width, which
can truncate a long name). `name.py` uses the line-2 anchor below to find
that line-3 candidate and corroborate it against whatever value sits under
the wrong label on the page.
"""
from __future__ import annotations

import re
from typing import Iterator

#: MRZ characters are always plain ASCII digits/letters/`<` — never
#: accented — so, unlike every field parser's own `normalize`, this needs
#: no accent-stripping, only whitespace removal (an OCR pass can insert a
#: stray space inside an otherwise-contiguous MRZ run) before the shape
#: regex below can match it. Self-contained on purpose: this module sits
#: BELOW every field parser (see the module docstring), so it does not
#: import `text.strip_accents_upper` or `gender.normalize` either, even
#: though both would incidentally work here.
_WS = re.compile(r"\s+")

#: Same shape and weights `gender.py` verifies for the sex letter — see this
#: module's own docstring for why sharing the anchor (not re-deriving it)
#: matters. Duplicated rather than imported from `gender.py` on purpose:
#: `gender.py` is itself a field parser (like `name.py`), and this module
#: is the shared PRIMITIVE the two of them sit on top of, not a dependency
#: of one on the other. The algorithm is a fixed ICAO 9303 standard (7-3-1
#: weighted sum mod 10) — it will not drift out of sync with `gender.py`'s
#: own copy.
_MRZ_LINE2_RE = re.compile(r"(?<![0-9A-Z<])(\d{6})(\d)([MF])(\d{6})(\d)([A-Z<]{3})")
_MRZ_PESOS = (7, 3, 1)


def _mrz_check(digitos: str) -> int:
    return sum(int(c) * _MRZ_PESOS[i % 3] for i, c in enumerate(digitos)) % 10


def line2_indices(text: str) -> Iterator[int]:
    """0-based line indices (matching `(text or "").splitlines()`) of every
    line that is a TD1 MRZ's dates+sex+expiry line with BOTH date check
    digits verified.

    RAW text in, like `gender._gender_from_mrz`: line breaks are the MRZ's
    own structure, so nothing here may collapse them first.
    """
    for i, linha in enumerate((text or "").splitlines()):
        compacta = _WS.sub("", linha).upper()
        for m in _MRZ_LINE2_RE.finditer(compacta):
            nasc, c1, _sexo, validade, c2, _nat = m.groups()
            if _mrz_check(nasc) == int(c1) and _mrz_check(validade) == int(c2):
                yield i
                break


__all__ = ["line2_indices"]
