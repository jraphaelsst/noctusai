"""ABNT renderers — plain text and `.docx` → `Paragraph`s, and a
`FormattedDocument` → an ABNT-formatted PDF or a Word-pasteable HTML
fragment.

WHY THIS IS SEPARATE FROM `formatting.py`
------------------------------------------
`formatting.py` holds only the value objects both directions share:
`FormatRange` offsets into plain text, and the `Run`/`Paragraph`/
`FormattedDocument` rendering-side shape. This module holds the two
directions that shape actually serves — BUILDING a `FormattedDocument`
from a source (plain text + offsets, or a `.docx`), and RENDERING one to
the two outputs the platform ships: a PDF (NBR 14724) and a Word-pasteable
HTML fragment. Builder and renderer never need each other; they meet only
at `FormattedDocument`.

ABNT BY CONSTRUCTION, NOT BY COPYING
-------------------------------------
Owner requirement (`projects/abnt-formatting-CONTRACT.md` §0.4): tudo
formatado em ABNT por construção, por padrão — nenhuma formatação copiada
dos arquivos de referência. The renderer decides margins, indents, line
spacing and page numbers from `ParagraphKind` alone; a source document's
own margins/fonts/spacing never reach the output. `Run.bold`/
`Run.underline` DO reach the output — that is CONTENT (owner requirement
§0.3), not layout. `TITLE`/`HEADING` are bold BY THE KIND regardless of the
source `Run`'s own `bold` flag, so a synthesized title string built via
`paragraphs_from_text` (which carries no formatting of its own) still
renders bold — the same "by construction" rule applied consistently.

FONT: CORE TIMES, NO EMBEDDING
-------------------------------
PDF: reportlab's core `Times-Roman`/`Times-Bold`, `WinAnsiEncoding` (a
cp1252 superset of Latin-1). Checked against every character pt-BR legal
documents use — ordinal indicators, section sign, en/em dash, curly
quotes, bullet, one-half, superscript two, and the accented capitals
`Ç Ã Õ É Ê Ô Ú` — all present in `WinAnsiEncoding`; see
`test_abnt_pdf.py::TestGlyphCoverage::test_winansi_covers_pt_br_legal_glyphs`
for the render-and-extract-back proof. No character has needed vendoring
Liberation Serif. If one ever does, `render_abnt_pdf` must raise naming it
— never drop it silently (see `_assert_renders_with_core_font` below).

DETERMINISM
------------
`reportlab.rl_config.invariant` fixes the PDF's `/CreationDate` and file
`/ID` for the build. It is a PROCESS-GLOBAL reportlab flag, so it is
toggled on only around this module's own `doc.build()` call and restored
in a `finally` — a concurrent reportlab consumer in the same process
(e.g. social-wiring's `roteiro_pdf_service`, which wants a real timestamp)
must never see it flipped.

Contract: `projects/abnt-formatting-CONTRACT.md` §3.
"""
from __future__ import annotations

import re
from typing import Callable, Optional, Sequence

from noctusai_lib.integrations.documents.formatting import (
    FormatRange,
    FormattedDocument,
    Paragraph,
    ParagraphKind,
    Run,
)

__all__ = [
    "UnsupportedGlyphError",
    "clip_ranges",
    "paragraphs_from_text",
    "paragraphs_from_docx",
    "render_abnt_pdf",
    "render_word_html",
    "runs_from_ranges",
]


class UnsupportedGlyphError(ValueError):
    """`render_abnt_pdf` found a character the core Times font's
    `WinAnsiEncoding` cannot represent. reportlab does NOT raise for this
    on its own — an unencodable glyph silently becomes a wrong glyph (a
    real, verified failure mode: an emoji rendered as `I`) — so this
    module checks first and raises NAMING the character, per the "never
    drop a character silently" contract clause. If this is ever raised
    on a real pt-BR legal document (as opposed to a genuinely foreign
    character), vendor Liberation Serif — see the module docstring."""


# ─── shared: escaping + inline markup ────────────────────────────────────
#
# Both renderers use the same three-character escape (contract-named:
# `&`, `<`, `>`) and the same bold/underline nesting — reportlab's
# Paragraph markup and an HTML fragment both understand `<b>`/`<u>`, and
# both treat an embedded "\n" as a line break, spelled `<br/>` in one and
# `<br>` in the other.


def _escape_markup(text: str) -> str:
    """`&` first, then `<`/`>` — the only three characters either markup
    dialect treats specially. Escaping `&` first matters, or a literal
    `&lt;` in the source would itself get re-escaped to `&amp;lt;`."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _run_markup(run: Run, *, force_bold: bool, br: str) -> str:
    text = _escape_markup(run.text).replace("\n", br)
    if run.bold or force_bold:
        text = f"<b>{text}</b>"
    if run.underline:
        text = f"<u>{text}</u>"
    return text


def _is_forced_bold_kind(kind: ParagraphKind) -> bool:
    """TITLE and HEADING are bold BY THE KIND — see module docstring."""
    return kind in (ParagraphKind.TITLE, ParagraphKind.HEADING)


# ─── run merging (shared by both builders) ───────────────────────────────


def _merge_adjacent_runs(runs: Sequence[Run]) -> tuple[Run, ...]:
    """Collapse consecutive `Run`s with identical `(bold, underline)` into
    one. Two `FormatRange`s that happen to abut with the same formatting
    (the boundary sweep in `paragraphs_from_text` splits at every
    boundary, so an unbroken bold stretch spanning two adjacent input
    ranges comes out as two `Run`s) must not render as a spurious
    mid-word split."""
    merged: list[Run] = []
    for run in runs:
        if merged and merged[-1].bold == run.bold and merged[-1].underline == run.underline:
            prev = merged.pop()
            merged.append(Run(text=prev.text + run.text, bold=prev.bold, underline=prev.underline))
        else:
            merged.append(run)
    return tuple(merged)


# ─── paragraphs_from_text ─────────────────────────────────────────────────

#: One-or-more blank lines. Requires at least two "\n" characters (a
#: single "\n" is a line break WITHIN a paragraph, not a separator); a run
#: of 2+ blank lines still collapses to exactly ONE paragraph break.
_PARAGRAPH_SEPARATOR = re.compile(r"\n[ \t]*(?:\n[ \t]*)+")


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    """`[start, end)` offsets of each paragraph's plain text, in the
    ORIGINAL `text`'s coordinates — computed before any splitting, so a
    `FormatRange` can be clipped and re-based per paragraph afterwards."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for match in _PARAGRAPH_SEPARATOR.finditer(text):
        spans.append((pos, match.start()))
        pos = match.end()
    spans.append((pos, len(text)))
    return spans


def clip_ranges(ranges: Sequence[FormatRange], start: int, end: int) -> list[FormatRange]:
    """`ranges` overlapping `[start, end)`, clipped to it and re-based to
    a `0` origin. A range crossing a boundary is clipped PER slice — the
    part outside `[start, end)` is simply not represented in this slice's
    output. Public: used both by `paragraphs_from_text` (per paragraph)
    and by a caller re-basing document-level ranges onto a SUB-slice of
    the owning text (e.g. a matrícula quote's selected acts, contract
    `projects/abnt-formatting-CONTRACT.md` §5)."""
    out: list[FormatRange] = []
    for r in ranges:
        lo, hi = max(r.start, start), min(r.end, end)
        if lo < hi:
            out.append(FormatRange(start=lo - start, end=hi - start, bold=r.bold, underline=r.underline))
    return out


def runs_from_ranges(paragraph_text: str, ranges: Sequence[FormatRange]) -> tuple[Run, ...]:
    """Split `paragraph_text` into `Run`s at every `FormatRange` boundary.
    `ranges` must already be LOCAL (0-origin) to `paragraph_text` — clip
    with `clip_ranges` first if they are not. Between two CONSECUTIVE
    breakpoints, every range either fully covers the segment or is fully
    outside it (breakpoints are exactly the set of range starts/ends, so
    a range boundary strictly inside a segment cannot exist) — so
    `bold`/`underline` for a segment is simply the OR over ranges
    covering it. Overlapping ranges therefore compose. Public: the
    flat (non-paragraph-split) building block a caller building a single
    docxtpl `RichText` context value from `(text, ranges)` needs directly
    — `paragraphs_from_text` is the paragraph-splitting caller of this
    same primitive."""
    if not paragraph_text:
        return ()
    breakpoints = sorted({0, len(paragraph_text), *(r.start for r in ranges), *(r.end for r in ranges)})
    runs: list[Run] = []
    for lo, hi in zip(breakpoints, breakpoints[1:]):
        bold = any(r.start <= lo and hi <= r.end and r.bold for r in ranges)
        underline = any(r.start <= lo and hi <= r.end and r.underline for r in ranges)
        runs.append(Run(text=paragraph_text[lo:hi], bold=bold, underline=underline))
    return _merge_adjacent_runs(runs)


def paragraphs_from_text(
    text: str,
    formatting: Sequence[FormatRange] = (),
    *,
    kind: ParagraphKind = ParagraphKind.BODY,
) -> tuple[Paragraph, ...]:
    """`text` (plain, as `Transcription.text`/`.formatting` produce it) →
    `Paragraph`s of one `kind`. One-or-more blank lines split paragraphs;
    a single `"\\n"` stays a line break inside a `Run`. Every
    `FormatRange` crossing a paragraph boundary is clipped per side;
    overlapping ranges compose (bold ∪ underline). An empty `text` (or
    one that is only blank lines) yields `()` — nothing to render."""
    out: list[Paragraph] = []
    for start, end in _paragraph_spans(text):
        if end <= start:
            continue
        local_ranges = clip_ranges(formatting, start, end)
        runs = runs_from_ranges(text[start:end], local_ranges)
        if runs:
            out.append(Paragraph(runs=runs, kind=kind))
    return tuple(out)


# ─── paragraphs_from_docx ─────────────────────────────────────────────────


def _resolve_run_flag(run, paragraph, attr: str) -> bool:
    """A run's OWN `bold`/`underline` wins when set; else walk its
    character style's `base_style` chain, then the paragraph style's own
    chain. A Word "Title"/"Heading N" style typically sets `bold` on the
    STYLE, not on every run pasted into it — the contract's `classify`
    mapping (slice S4) depends on that being resolved here rather than
    left `None` (python-docx's "inherit" sentinel)."""
    value = getattr(run, attr, None)
    if value is not None:
        return bool(value)
    style = run.style
    while style is not None:
        font = getattr(style, "font", None)
        value = getattr(font, attr, None) if font is not None else None
        if value is not None:
            return bool(value)
        style = getattr(style, "base_style", None)
    style = paragraph.style
    while style is not None:
        font = getattr(style, "font", None)
        value = getattr(font, attr, None) if font is not None else None
        if value is not None:
            return bool(value)
        style = getattr(style, "base_style", None)
    return False


def paragraphs_from_docx(
    docx: bytes,
    *,
    classify: Optional[Callable[[str, str], ParagraphKind]] = None,
) -> tuple[Paragraph, ...]:
    """A `.docx`'s paragraphs → `Paragraph`s. `classify(style_name, text)`
    picks each `ParagraphKind` (default: every paragraph is `BODY`).
    Empty paragraphs (no runs, or only empty-text runs) are dropped;
    adjacent runs with identical bold/underline are merged.

    Imports `python-docx` lazily — declared in `pyproject.toml` for
    `check_seed_declared_imports`, but a caller who only needs
    `paragraphs_from_text` should not need it importable."""
    import io

    from docx import Document as _DocxDocument

    document = _DocxDocument(io.BytesIO(docx))
    out: list[Paragraph] = []
    for paragraph in document.paragraphs:
        runs = tuple(
            Run(
                text=run.text,
                bold=_resolve_run_flag(run, paragraph, "bold"),
                underline=_resolve_run_flag(run, paragraph, "underline"),
            )
            for run in paragraph.runs
            if run.text
        )
        merged = _merge_adjacent_runs(runs)
        if not merged:
            continue
        style_name = paragraph.style.name if paragraph.style is not None else ""
        text = "".join(r.text for r in merged)
        kind = classify(style_name, text) if classify is not None else ParagraphKind.BODY
        out.append(Paragraph(runs=merged, kind=kind))
    return tuple(out)


# ─── render_abnt_pdf ───────────────────────────────────────────────────────

_PDF_FONT_SIZE_BODY = 12
_PDF_LEADING_BODY = 18  # 12pt × 1.5 line spacing
_PDF_FONT_SIZE_QUOTE = 10
_PDF_LEADING_QUOTE = 10  # single spacing


def _pdf_styles() -> dict:
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm

    return {
        ParagraphKind.TITLE: ParagraphStyle(
            "ABNTTitle",
            fontName="Times-Roman",
            fontSize=_PDF_FONT_SIZE_BODY,
            leading=_PDF_LEADING_BODY,
            alignment=TA_CENTER,
            spaceAfter=_PDF_LEADING_BODY,  # "followed by one blank line"
        ),
        ParagraphKind.HEADING: ParagraphStyle(
            "ABNTHeading",
            fontName="Times-Roman",
            fontSize=_PDF_FONT_SIZE_BODY,
            leading=_PDF_LEADING_BODY,
            alignment=TA_LEFT,
        ),
        ParagraphKind.BODY: ParagraphStyle(
            "ABNTBody",
            fontName="Times-Roman",
            fontSize=_PDF_FONT_SIZE_BODY,
            leading=_PDF_LEADING_BODY,
            alignment=TA_JUSTIFY,
            firstLineIndent=1.25 * cm,
            # reportlab already defaults justifyBreaks=0 (never stretch the
            # line immediately before an explicit <br/>); set explicitly so
            # a future reportlab default change cannot silently regress the
            # "no ugly stretched justification before a hard wrap" contract
            # clause.
            justifyBreaks=0,
        ),
        ParagraphKind.QUOTE: ParagraphStyle(
            "ABNTQuote",
            fontName="Times-Roman",
            fontSize=_PDF_FONT_SIZE_QUOTE,
            leading=_PDF_LEADING_QUOTE,
            alignment=TA_JUSTIFY,
            leftIndent=4 * cm,
            justifyBreaks=0,
        ),
    }


def _draw_page_number(canvas, doc) -> None:
    from reportlab.lib.units import cm

    canvas.saveState()
    canvas.setFont("Times-Roman", 10)
    canvas.drawRightString(doc.pagesize[0] - 2 * cm, doc.pagesize[1] - 1.5 * cm, str(canvas.getPageNumber()))
    canvas.restoreState()


def _no_page_number(canvas, doc) -> None:  # page 1 carries no number
    return None


#: The core Times font's `WinAnsiEncoding` is, byte-for-byte, Windows-1252
#: — Python's `cp1252` codec IS that encoding, so it is the correct (not
#: an approximating) pre-flight check; no reportlab-internal table needs
#: duplicating. Verified against every character pt-BR legal documents use
#: (ordinal indicators, section sign, en/em dash, curly quotes, bullet,
#: one-half, superscript two, accented capitals) — see
#: `test_abnt_pdf.py::TestGlyphCoverage::test_winansi_covers_pt_br_legal_glyphs`.
_CORE_FONT_ENCODING = "cp1252"


def _assert_renders_with_core_font(doc: FormattedDocument) -> None:
    """Raise `UnsupportedGlyphError`, naming the character, for anything
    the core Times font cannot represent — see that class's docstring for
    why this check exists instead of trusting reportlab."""
    texts = [doc.title or ""]
    texts.extend(run.text for paragraph in doc.paragraphs for run in paragraph.runs)
    for text in texts:
        try:
            text.encode(_CORE_FONT_ENCODING)
        except UnicodeEncodeError as exc:
            bad = text[exc.start : exc.end]
            raise UnsupportedGlyphError(
                f"render_abnt_pdf: character {bad!r} (U+{ord(bad[0]):04X}) has no "
                "representation in the core Times font's WinAnsiEncoding. Vendor "
                "Liberation Serif instead of dropping it — see module docstring."
            ) from exc


def render_abnt_pdf(doc: FormattedDocument) -> bytes:
    """`FormattedDocument` → ABNT-formatted (NBR 14724) PDF bytes. A4,
    margins top/left/bottom/right 3/3/2/2 cm, core Times 12pt (10pt for
    `QUOTE`), page numbers top-right from page 2. Deterministic for
    identical input — see module docstring.

    Raises `UnsupportedGlyphError`, naming the character, for anything
    the core Times font cannot represent — see that class's docstring.

    Imports `reportlab` lazily — declared in `pyproject.toml` for
    `check_seed_declared_imports`, but a caller who only needs
    `render_word_html` should not need it importable."""
    import io

    from reportlab import rl_config
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph as _RLParagraph
    from reportlab.platypus import SimpleDocTemplate

    _assert_renders_with_core_font(doc)

    styles = _pdf_styles()
    story = []
    for paragraph in doc.paragraphs:
        force_bold = _is_forced_bold_kind(paragraph.kind)
        markup = "".join(_run_markup(r, force_bold=force_bold, br="<br/>") for r in paragraph.runs)
        story.append(_RLParagraph(markup, styles[paragraph.kind]))

    buffer = io.BytesIO()
    pdf_doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=3 * cm,
        leftMargin=3 * cm,
        bottomMargin=2 * cm,
        rightMargin=2 * cm,
        title=doc.title or "",
        author="",
        subject="",
        creator="NoctusAI",
    )

    # `rl_config.invariant` is a PROCESS-GLOBAL flag (see module
    # docstring) — flip it only around this build, restore unconditionally.
    previous_invariant = rl_config.invariant
    rl_config.invariant = 1
    try:
        pdf_doc.build(story, onFirstPage=_no_page_number, onLaterPages=_draw_page_number)
    finally:
        rl_config.invariant = previous_invariant
    return buffer.getvalue()


# ─── render_word_html ──────────────────────────────────────────────────────

# SINGLE-quoted font-family value on purpose: the fragment's OWN attribute
# delimiter is double-quoted (`style="..."`, matching the contract's
# "inline styles only" HTML), so a double-quoted "Times New Roman" here
# would close the `style` attribute early at the first embedded `"` and
# corrupt the fragment — CSS accepts either quote style for a font-family
# string, so single-quoting the family name is the only one that nests
# correctly inside a double-quoted HTML attribute.
_HTML_BASE_FONT = "font-family:'Times New Roman', Times, serif; font-size:12pt; line-height:1.5;"
_HTML_STYLES = {
    ParagraphKind.BODY: _HTML_BASE_FONT + " text-align:justify; text-indent:1.25cm;",
    ParagraphKind.TITLE: _HTML_BASE_FONT + " text-align:center; font-weight:bold;",
    ParagraphKind.HEADING: _HTML_BASE_FONT + " font-weight:bold;",
    ParagraphKind.QUOTE: (
        "font-family:'Times New Roman', Times, serif; font-size:10pt; "
        "line-height:1; margin-left:4cm; text-align:justify;"
    ),
}


def render_word_html(doc: FormattedDocument) -> str:
    """`FormattedDocument` → a self-contained HTML fragment, inline
    styles only (Word ignores a `<style>` block on paste). `Run.bold`/
    `.underline` become `<b>`/`<u>`, combinable; `"\\n"` becomes `<br>`;
    all text is HTML-escaped."""
    parts = []
    for paragraph in doc.paragraphs:
        force_bold = _is_forced_bold_kind(paragraph.kind)
        inner = "".join(_run_markup(r, force_bold=force_bold, br="<br>") for r in paragraph.runs)
        parts.append(f'<p style="{_HTML_STYLES[paragraph.kind]}">{inner}</p>')
    return "\n".join(parts)
