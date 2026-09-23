"""Strip literal `**` / `<u>` markers — and, since 2026-09-23,
`pdf_text`-style provenance/validation boilerplate — out of an
ALREADY-STORED transcription, and say exactly how every offset into it
moves.

`remover_marcacao` (markers) and `remover_boilerplate` (registry stamps)
are the two independent removal passes; `backfill_service.normalizar_extracao`
composes them sequentially and chains their two `mapear` functions, because
each is verified against its own reconstruction independently and
composing two correct maps is simpler to get right than one function that
tries to do both removals at once.

WHY THIS EXISTS
---------------
Transcriptions made before `parse_markup` ran on the vision reply (migration
113) kept the model's markers in the text: `**IMÓVEL:** Apartamento ...`.
That text cannot go into a deed (the contract generator refuses it), and it
breaks every line-start parser downstream — `segmentar_abertura` never sees
`IMÓVEL:` at the start of a line, so those rows have no abertura blocks.

Re-transcribing costs a paid vision pass (and a pre-135 row has no source PDF
left to re-read). But the markers ARE the formatting, losslessly: running the
same `parse_markup` over the stored text yields the clean text AND the bold /
underline ranges a fresh transcription would have produced.

🔴 OFFSETS MUST MOVE WITH THE TEXT
----------------------------------
Everything structured about a matrícula is an OFFSET into its text — acts,
abertura blocks, page-noise spans, qualification name spans, the título/ônus
pointers. Removing characters shifts every one after them. `mapear` is the
one function every such column is rewritten through, so the rewrite is a pure
function of the removed spans and can never disagree with the text.

🔴 ONE DERIVATION, NOT TWO
--------------------------
Which markers are removed is decided by `transcription.parse_markup`'s own
token scan and its own balancing rules (an unbalanced `**` stays literal) —
imported, never re-derived — and the result is checked against
`parse_markup`'s output before it is returned. A mismatch raises: a clean text
whose offsets are wrong would quote the wrong bytes into a legal instrument.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from noctusai_lib.integrations.documents.formatting import FormatRange
from noctusai_lib.integrations.documents.transcription import (
    _MARKUP_TOKEN_RE,
    _unmatched_pair_indices,
    _unmatched_toggle_index,
    parse_markup,
)


@dataclass(frozen=True)
class MarcacaoRemovida:
    """The clean text, its formatting, and the spans removed from the
    ORIGINAL text (sorted, non-overlapping, `[start, end)`)."""

    texto: str
    formatacao: tuple[FormatRange, ...]
    removidos: tuple[tuple[int, int], ...]

    @property
    def alterou(self) -> bool:
        return bool(self.removidos)

    def mapear(self, offset: int) -> int:
        """An offset into the ORIGINAL text → the same position in `texto`.

        Characters removed before `offset` are subtracted; an offset that
        falls INSIDE a removed marker lands on the marker's start (a marker
        has no bytes of its own left to point into).
        """
        if not self.removidos:
            return offset
        inicios = [s for s, _ in self.removidos]
        k = bisect_right(inicios, offset)
        deslocamento = 0
        for s, e in self.removidos[:k]:
            deslocamento += min(e, offset) - s if offset < e else e - s
        return offset - deslocamento


def remover_boilerplate(texto: str) -> MarcacaoRemovida:
    """`texto` with every registry provenance/validation stamp removed —
    the SAME offset-tracking shape as `remover_marcacao`, so a caller can
    compose the two: `r1 = remover_marcacao(texto); r2 =
    remover_boilerplate(r1.texto)`, then move every downstream offset
    through BOTH via `r2.mapear(r1.mapear(offset))`.

    Line-based, not token-based: a removed span is one whole boilerplate
    LINE, its own trailing newline included, from
    `media.boilerplate_line_spans` — the SAME predicate
    `pdf_text.clean_extraction_output` uses at fresh-extraction time, so a
    backfilled row and a freshly-transcribed one can never disagree about
    what counts as boilerplate. `formatacao` is always `()`: removing a
    stamp line never ADDS a bold/underline range — only `remover_marcacao`
    does that, by construction.

    Unlike `clean_extraction_output`, this does NOT trim a leading/
    trailing blank line left behind by a removed stamp: every character
    NOT accounted for by `removidos` must survive unchanged, or `mapear`
    would silently misplace an offset into an act, an abertura block, or a
    qualification name span — the exact failure `remover_marcacao`'s own
    reconstruction check guards against.
    """
    texto = texto or ""
    from noctusai_lib.integrations.media import boilerplate_line_spans

    removidos = boilerplate_line_spans(texto)
    reconstruido = []
    cursor = 0
    for s, e in removidos:
        reconstruido.append(texto[cursor:s])
        cursor = e
    reconstruido.append(texto[cursor:])
    return MarcacaoRemovida(texto="".join(reconstruido), formatacao=(), removidos=removidos)


def remover_marcacao(texto: str) -> MarcacaoRemovida:
    """`texto` with every well-formed marker removed — see module docstring."""
    texto = texto or ""
    tokens: list[tuple[str, int, int]] = []
    pos = 0
    for m in _MARKUP_TOKEN_RE.finditer(texto):
        if m.start() > pos:
            tokens.append(("text", pos, m.start()))
        bruto = m.group()
        if bruto == "**":
            kind = "bold"
        elif bruto.lower() == "<u>":
            kind = "u_open"
        else:
            kind = "u_close"
        tokens.append((kind, m.start(), m.end()))
        pos = m.end()
    if pos < len(texto):
        tokens.append(("text", pos, len(texto)))

    literais = set(_unmatched_toggle_index(tokens, "bold"))
    abertos, fechamentos = _unmatched_pair_indices(tokens, "u_open", "u_close")
    literais |= abertos | fechamentos

    removidos = tuple(
        (s, e)
        for i, (kind, s, e) in enumerate(tokens)
        if kind != "text" and i not in literais
    )
    limpo, formatacao = parse_markup(texto)

    reconstruido = []
    cursor = 0
    for s, e in removidos:
        reconstruido.append(texto[cursor:s])
        cursor = e
    reconstruido.append(texto[cursor:])
    if "".join(reconstruido) != limpo:
        raise ValueError(
            "remover_marcacao: removed spans disagree with parse_markup — "
            "refusing to hand back offsets that would quote the wrong bytes"
        )
    return MarcacaoRemovida(texto=limpo, formatacao=formatacao, removidos=removidos)


__all__ = ["MarcacaoRemovida", "remover_boilerplate", "remover_marcacao"]
