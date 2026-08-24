"""Accent/case normalisation shared by the field parsers.

Extracted because the two parsers need the SAME character handling and
OPPOSITE whitespace handling, and conflating those is how one of them
silently gets the other's rules.

- `birthdate` collapses newlines into spaces: a label and its date are
  routinely split across a line break by OCR, and the date regex finds
  the value wherever it sits, so line structure is pure noise there.
- `name` must PRESERVE lines: a name has no self-delimiting shape, so the
  end of the line is the only thing that says where it stops. Collapse the
  newlines and `NOME\\nFULANO DE TAL\\nFILIACAO` becomes one run of words
  with no boundary between the person and their parents.
"""
from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"[ \t\f\v ]+")


def strip_accents_upper(text: str) -> str:
    """NFKD-decompose, drop combining marks, uppercase.

    Accents go because OCR is unreliable about them and a label written
    `FILIAÇÃO` must match `FILIACAO`. Uppercasing follows because Brazilian
    ID layouts are already uppercase and case carries no signal here.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()


def normalize_lines(text: str) -> list[str]:
    """Normalised, non-empty lines with intra-line whitespace collapsed.

    Line ORDER and line BREAKS survive; everything else is flattened.
    """
    flat = strip_accents_upper(text)
    out: list[str] = []
    for raw in flat.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _WS.sub(" ", raw).strip()
        if line:
            out.append(line)
    return out


__all__ = ["normalize_lines", "strip_accents_upper"]
