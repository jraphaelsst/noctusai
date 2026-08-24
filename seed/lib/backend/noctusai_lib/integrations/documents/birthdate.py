"""Label-anchored birthdate extraction from Brazilian identity-document text.

Pure — no IO, no LLM, no network. Give it text, get a date and a
confidence. That makes the part of this feature most likely to be *subtly*
wrong the part that is cheapest to test.

WHY NOT "THE FIRST DATE IN THE DOCUMENT"
---------------------------------------
A Brazilian RG carries up to four dates — nascimento, expedição, emissão
and validade — and on the standard layout the **expedição date is printed
above the birthdate**. A CNH adds "data da primeira habilitação". So
positional extraction ("take the first date") is not merely imprecise, it
is wrong more often than it is right, and it fails silently: the value it
produces is a real, plausible date.

So this module anchors on labels, and it anchors *negatively* too: a date
whose nearest preceding label is `VALIDADE` is not a birthdate no matter
how plausible it looks.

THE SANITY GATE
---------------
Even a correctly-anchored date can be an OCR misread. Every candidate must
land in the past and imply an age in `[MIN_AGE, MAX_AGE]`. A parsed
`12/05/2027` is a validade that leaked past the label check, not a person
born in the future; a parsed `12/05/1830` is a digit confusion. Both are
dropped rather than reported at low confidence, because "implausible" is
information, not noise.

TWO DELIBERATE OMISSIONS
------------------------
- **Two-digit years are not parsed.** `12/05/80` is genuinely ambiguous
  (1980? 2080?) and resolving it by pivot-year convention would
  manufacture confidence this module has no basis for.
- **No fuzzy digit repair.** Rewriting `l980` to `1980` would let the
  extractor invent the very digits it is least sure about.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from noctusai_lib.integrations.documents.text import strip_accents_upper

#: Plausible human age range for someone in a CRM as a lead/client.
#: The lower bound is deliberately not 0 — a birthdate implying a
#: 3-year-old is a misread, not a toddler buying property.
MIN_AGE = 16
MAX_AGE = 120

#: How far back from a date we look for its label. Wide enough to span the
#: whitespace/newline noise OCR inserts between a label and its value,
#: narrow enough that the *previous* field's label cannot claim it.
_LABEL_WINDOW = 48

_MONTHS = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4,
    "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
    "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}

#: Labels that mark the following date AS the birthdate. Longest-first so
#: `DATA DE NASCIMENTO` wins over the bare `NASC` nested inside it.
_BIRTH_LABELS = (
    "DATA DE NASCIMENTO",
    "DATA NASCIMENTO",
    "DT NASCIMENTO",
    "DATA DE NASC",
    "DATA NASC",
    "DT NASC",
    "NASCIMENTO",
    "NASCIDO EM",
    "NASCIDA EM",
    "NASC",
)

#: Labels that mark the following date as something that is definitely NOT
#: a birthdate. Present so the common layouts actively exclude their
#: decoys rather than relying on the birth label winning a proximity race.
_DECOY_LABELS = (
    "DATA DA PRIMEIRA HABILITACAO",
    "PRIMEIRA HABILITACAO",
    "DATA DE EXPEDICAO",
    "DATA EXPEDICAO",
    "DATA DE EMISSAO",
    "DATA EMISSAO",
    "DATA DE VALIDADE",
    "DATA DE REGISTRO",
    "EXPEDIDO EM",
    "EXPEDIDA EM",
    "EMITIDO EM",
    "EMITIDA EM",
    "REGISTRADO EM",
    "VALIDA ATE",
    "VALIDO ATE",
    "EXPEDICAO",
    "EMISSAO",
    "VALIDADE",
    "HABILITACAO",
)

_NUMERIC_DATE = re.compile(r"\b(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})\b")
_TEXTUAL_DATE = re.compile(
    r"\b(\d{1,2})\s+DE\s+(" + "|".join(_MONTHS) + r")\s+DE\s+(\d{4})\b"
)


def normalize(text: str) -> str:
    """Uppercase, strip accents, collapse whitespace.

    Newlines collapse to single spaces on purpose: OCR routinely splits a
    label from its value across a line break, and the `_LABEL_WINDOW`
    proximity rule is what keeps that from over-reaching.
    """
    return re.sub(r"\s+", " ", strip_accents_upper(text)).strip()


def _label_before(haystack: str, at: int) -> tuple[Optional[str], bool]:
    """Nearest label preceding position `at`, and whether it is a decoy.

    "Nearest" is what makes the decoy list work: on a layout where both
    `EXPEDICAO` and `NASCIMENTO` appear before a date, only the closer one
    describes it.
    """
    window = haystack[max(0, at - _LABEL_WINDOW):at]
    best: tuple[int, str, bool] | None = None
    for label, is_decoy in (
        [(x, False) for x in _BIRTH_LABELS] + [(x, True) for x in _DECOY_LABELS]
    ):
        pos = window.rfind(label)
        if pos == -1:
            continue
        # Prefer the label that ENDS latest (closest to the date); break a
        # tie toward the longer label so `DATA DE NASCIMENTO` beats `NASC`.
        end = pos + len(label)
        if best is None or (end, len(label)) > (best[0], len(best[1])):
            best = (end, label, is_decoy)
    if best is None:
        return (None, False)
    return (best[1], best[2])


def _plausible(d: date, today: date) -> bool:
    """A birthdate must be in the past and imply a credible age."""
    if d > today:
        return False
    age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    return MIN_AGE <= age <= MAX_AGE


def _iter_dates(text: str):
    """Every parseable date with its start offset. Malformed values (day
    32, month 13) are skipped here rather than raising — a document may
    legitimately contain a number that merely looks like a date."""
    for m in _NUMERIC_DATE.finditer(text):
        day, month, year = (int(g) for g in m.groups())
        try:
            yield (m.start(), date(year, month, day))
        except ValueError:
            continue
    for m in _TEXTUAL_DATE.finditer(text):
        day, month_name, year = m.group(1), m.group(2), m.group(3)
        try:
            yield (m.start(), date(int(year), _MONTHS[month_name], int(day)))
        except ValueError:
            continue


def find_birthdate(
    text: str,
    *,
    today: Optional[date] = None,
) -> tuple[Optional[date], str, Optional[str]]:
    """Extract a birthdate.

    Returns `(value, confidence, matched_label)` where confidence is one
    of `"alta"` / `"baixa"` / `"nenhuma"` — the string values of
    `types.ExtractionConfidence`, kept as plain strings so this module
    stays import-free of the rest of the package.

    - **alta** — label-anchored and plausible. If several labelled dates
      are found they must all agree; disagreement means the layout was
      misread, so it degrades rather than picking a winner.
    - **baixa** — exactly one unlabelled-but-plausible date in the whole
      document. Genuinely a guess, and typed as one.
    - **nenhuma** — nothing, or too many candidates to choose between.
      Ambiguity is reported as absence, never resolved by guessing.
    """
    today = today or date.today()
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma", None)

    labelled: list[tuple[date, str]] = []
    unlabelled: list[date] = []

    for offset, value in _iter_dates(norm):
        if not _plausible(value, today):
            continue
        label, is_decoy = _label_before(norm, offset)
        if is_decoy:
            continue
        if label:
            labelled.append((value, label))
        else:
            unlabelled.append(value)

    if labelled:
        distinct = {v for v, _ in labelled}
        if len(distinct) == 1:
            value, label = labelled[0]
            return (value, "alta", label)
        # Two different dates both claiming to be the birthdate: the
        # layout was misread. Report the ambiguity instead of resolving it.
        return (None, "nenhuma", None)

    if len(unlabelled) == 1:
        return (unlabelled[0], "baixa", None)

    return (None, "nenhuma", None)


__all__ = ["MAX_AGE", "MIN_AGE", "find_birthdate", "normalize"]
