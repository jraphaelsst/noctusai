"""Segment a literal matrícula transcription into its acts — as OFFSETS.

A certidão de matrícula is an append-only ledger: an opening block (the
property description, the owner at opening, the registro anterior) followed
by numbered acts — registros (`R-1`, `R.2`, `R 03`) and averbações (`AV-4`,
`Av.5`, `AV.06/12.345`). A contract quotes those acts, and the operator picks
which ones.

🔴 OFFSETS, NEVER TEXT
----------------------
The contract must quote the matrícula LITERALLY — typos, odd spacing, OCR
artefacts included — because a cartório compares the quote against its own
book. So this module never returns a rewritten string. Every record is a
`(start, end)` pair into the caller's input, and `text[start:end]` is the
quote, byte-identical.

`normalize` (from `matricula.py`) is used ONLY to match headers. It is applied
per character so every normalised position maps back to exactly one original
offset; whitespace is kept verbatim so line structure survives for matching.

🔴 NOTHING IS DROPPED
---------------------
The returned spans are contiguous and cover the whole input: span[0].start is
0, each span starts where the previous one ended, the last one ends at
len(text). A header this module is not confident about is NOT a boundary — its
text stays inside the previous span, so the worst misread is "two acts shown
as one", never "an act lost".

What counts as a header
-----------------------
`R` or `AV` (any case, accents irrelevant), an optional `-` / `.` separator
with OCR spacing tolerated, a 1–4 digit act number, and an optional matrícula
suffix (`/12.345`, `/M.12345`, `-12.345`). Then, by position:

- **At the start of a line** (only horizontal whitespace before it) — accepted
  when the token is not glued to a following letter/digit. Transcription joins
  pages with blank lines, so a header after a page join lands here.
- **Mid-line** — accepted only right after a sentence terminator (`.` `;` `:`)
  AND followed by a dash or colon separator. This is the "OCR merged the next
  header into the last line of the previous act" case; anything looser would
  split acts on body citations ("cancelamento do R-3").

A repeated `(kind, numero)` is a citation, not a new act, and is ignored.
Everything before the first accepted header is the abertura (omitted when
empty).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

from noctusai_lib.integrations.documents.matricula import normalize

AtoKind = Literal["abertura", "R", "AV"]

_H = r"[^\S\r\n]"  # horizontal whitespace

#: The header token, matched against the per-char normalised text.
_HEADER = re.compile(
    rf"(?<![A-Z0-9])"
    rf"(?P<kind>AV|R)"
    rf"{_H}*[-.–—]?{_H}*"
    rf"(?P<num>\d{{1,4}})(?!\d)(?!,\d)"
    rf"(?P<suffix>"
    rf"{_H}*/{_H}*(?:M{_H}*[.-]?{_H}*)?\d+(?:\.\d+)*"
    # Dash suffix only when glued (`R.6-9.876`): `R-1 - 2020` is a date.
    rf"|-(?:M\.?)?(?:\d{{1,3}}(?:\.\d{{3}})+|\d{{4,}})"
    rf")?"
)

#: Separator required after a MID-LINE header.
_MIDLINE_TAIL = re.compile(rf"{_H}*[-:–—]")

#: Terminators after which a mid-line header may begin.
_TERMINATORS = ".;:"


@dataclass(frozen=True)
class MatriculaAto:
    """One act of a matrícula, as offsets into the transcription.

    `start`/`end` delimit the whole act (quote it with `text[start:end]`).
    `header_start`/`header_end` delimit the recognised header token
    (`R-1/12.345`) for UI highlighting; both are None for the abertura.
    `numero` is the act number as an int (`R 01` → 1); None for the abertura.
    """

    kind: AtoKind
    numero: Optional[int]
    start: int
    end: int
    header_start: Optional[int] = None
    header_end: Optional[int] = None

    def quote(self, text: str) -> str:
        """The literal act text — `text[start:end]`, never rewritten."""
        return text[self.start : self.end]


def _normalized_with_offsets(text: str) -> tuple[str, list[int]]:
    """Per-char normalised text plus, for each normalised char, the offset of
    the original char it came from. Whitespace is kept verbatim (so `\\n`
    survives); a char that normalises to nothing (a lone combining mark)
    contributes no position."""
    parts: list[str] = []
    origem: list[int] = []
    for i, c in enumerate(text):
        n = c if c.isspace() else normalize(c)
        parts.append(n)
        origem.extend([i] * len(n))
    return "".join(parts), origem


def _accept(norm: str, m: re.Match[str]) -> bool:
    inicio = norm.rfind("\n", 0, m.start()) + 1
    antes = norm[inicio : m.start()]
    fim = m.end()
    if not antes.strip():
        # Line start: the token must end at a non-alphanumeric boundary.
        return fim >= len(norm) or not norm[fim].isalnum()
    anterior = antes.rstrip()
    if anterior and anterior[-1] in _TERMINATORS and antes != anterior:
        return _MIDLINE_TAIL.match(norm, fim) is not None
    return False


def segment_matricula_atos(text: str) -> list[MatriculaAto]:
    """Split a literal matrícula transcription into ordered acts.

    Returns contiguous spans covering ALL of `text` (empty input → `[]`).
    Unrecognised or doubtful headers never split a span; see module docstring.
    """
    if not text:
        return []
    norm, origem = _normalized_with_offsets(text)

    def to_orig_start(k: int) -> int:
        return origem[k] if k < len(origem) else len(text)

    def to_orig_end(k: int) -> int:
        return origem[k - 1] + 1 if k > 0 else 0

    cabecalhos: list[tuple[str, int, int, int]] = []
    vistos: set[tuple[str, int]] = set()
    for m in _HEADER.finditer(norm):
        if not _accept(norm, m):
            continue
        chave = (m.group("kind"), int(m.group("num")))
        if chave in vistos:
            continue
        vistos.add(chave)
        cabecalhos.append(
            (chave[0], chave[1], to_orig_start(m.start()), to_orig_end(m.end()))
        )

    atos: list[MatriculaAto] = []
    primeiro = cabecalhos[0][2] if cabecalhos else len(text)
    if primeiro > 0:
        atos.append(MatriculaAto(kind="abertura", numero=None, start=0, end=primeiro))
    for idx, (kind, numero, h_start, h_end) in enumerate(cabecalhos):
        fim = cabecalhos[idx + 1][2] if idx + 1 < len(cabecalhos) else len(text)
        atos.append(
            MatriculaAto(
                kind=kind,  # type: ignore[arg-type]
                numero=numero,
                start=h_start,
                end=fim,
                header_start=h_start,
                header_end=h_end,
            )
        )
    return atos


def ato_hint_span(text: str, ato: MatriculaAto) -> tuple[int, int]:
    """Offsets of the act's first non-blank line, trimmed — a label for the
    UI (`R-1/12.345 - Em 10 de março ... VENDA`). Still offsets: slice `text`
    with them. Returns `(ato.start, ato.start)` for an all-blank span."""
    pos = ato.start
    while pos < ato.end:
        quebra = text.find("\n", pos, ato.end)
        fim_linha = ato.end if quebra < 0 else quebra
        linha = text[pos:fim_linha]
        if linha.strip():
            ini = pos + (len(linha) - len(linha.lstrip()))
            fim = pos + len(linha.rstrip())
            return (ini, fim)
        pos = fim_linha + 1
    return (ato.start, ato.start)


__all__ = ["AtoKind", "MatriculaAto", "ato_hint_span", "segment_matricula_atos"]
