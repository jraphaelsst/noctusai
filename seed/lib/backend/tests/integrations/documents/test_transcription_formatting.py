"""ABNT formatting — slice S1: the seed transcriber captures bold/underline.

Contract: `projects/abnt-formatting-CONTRACT.md` §1-2.

Two independent sources feed `TranscribedPage.formatting`:

- Rung 1 (text layer): PyMuPDF spans (bold) + `get_drawings()` (underline),
  aligned onto the page's OWN trusted text. Exercised here against REAL
  synthetic PDFs built with PyMuPDF — the alignment logic (`str.find`,
  merging, dropping an unmatched span) is exactly what would silently shift
  an existing matrícula-act offset if it were wrong, so it is worth paying
  for real bytes rather than stubbing PyMuPDF out.
- Rung 2 (vision): a marked-up reply (`**bold**`, `<u>underline</u>`) parsed
  by the pure `parse_markup` function. Exercised both as a pure parser
  (no PDF at all) and end-to-end through `LadderDocumentTranscriber` with an
  injected `analyze` callable — the seam the module already offers, not a
  patch of the module's own code (`KB § PATTERNS/backend/di-test-seam.md`).

🔴 The single invariant every test here defends: `page.text` — and
therefore `Transcription.text` — is IDENTICAL to what it was before this
feature existed. A `FormatRange` is a second, optional layer; it must never
be able to change a single character of the first.
"""
from __future__ import annotations

import fitz  # type: ignore  # PyMuPDF
import pytest

from noctusai_lib.integrations.documents.formatting import FormatRange
from noctusai_lib.integrations.documents.transcription import (
    LadderDocumentTranscriber,
    OCR_PROMPT,
    _extract_text_layer_formatting,
    _has_underline,
    _is_bold_span,
    _merge_adjacent_ranges,
    parse_markup,
)
from noctusai_lib.integrations.documents.types import TextSource
from noctusai_lib.integrations.media import classify_pdf_text_layer


# ---------------------------------------------------------------------------
# Synthetic PDF builders
# ---------------------------------------------------------------------------
#
# Every builder writes at least `MIN_CHARS_PER_PAGE` (100) characters of
# plain filler so `classify_pdf_text_layer` classifies the page as
# substantive on its own merits — a page that only cleared the floor because
# the test author under-counted would be an accident, not a fixture.

_PREENCHIMENTO = (
    "Registro de imoveis para fins exclusivos de teste automatizado desta "
    "biblioteca, sem qualquer valor juridico ou probatorio real."
)


def _pdf_bold_and_underline() -> bytes:
    """One page: plain filler, a bold line, and a separately-underlined
    line — the two rung-1 signals in one document."""
    doc = fitz.open()
    page = doc.new_page()
    y = 72.0
    page.insert_text((72, y), _PREENCHIMENTO[:60], fontsize=11)
    y += 16
    page.insert_text((72, y), _PREENCHIMENTO[60:], fontsize=11)
    y += 24
    page.insert_text((72, y), "Titular do dominio", fontsize=11, fontname="Helvetica-Bold")
    y += 24
    baseline_sublinhado = y
    page.insert_text((72, y), "Onus e gravames vigentes", fontsize=11)
    page.draw_line(
        (72, baseline_sublinhado + 1.5), (72 + 140, baseline_sublinhado + 1.5), width=0.75
    )
    b = doc.tobytes()
    doc.close()
    return b


def _pdf_bold_and_underline_combined() -> bytes:
    """A single run that is BOTH bold and underlined — the combination
    the contract requires (`FormatRange(bold=True, underline=True)`)."""
    doc = fitz.open()
    page = doc.new_page()
    y = 72.0
    page.insert_text((72, y), _PREENCHIMENTO[:60], fontsize=11)
    y += 16
    page.insert_text((72, y), _PREENCHIMENTO[60:], fontsize=11)
    y += 24
    baseline = y
    page.insert_text((72, y), "Averbacao de onus real", fontsize=11, fontname="Helvetica-Bold")
    page.draw_line((72, baseline + 1.5), (72 + 140, baseline + 1.5), width=0.75)
    b = doc.tobytes()
    doc.close()
    return b


def _pdf_plain_only() -> bytes:
    """No formatting at all — the control document for the byte-identity
    proof (rung 1 must be a complete no-op on ordinary text)."""
    doc = fitz.open()
    page = doc.new_page()
    y = 72.0
    for _ in range(3):
        page.insert_text((72, y), _PREENCHIMENTO, fontsize=11)
        y += 16
    b = doc.tobytes()
    doc.close()
    return b


def _pdf_multi_page_mixed() -> bytes:
    """Two substantive pages, formatting on the second only — exercises
    `Transcription.formatting` re-basing across the "\\n\\n" page join."""
    doc = fitz.open()
    p1 = doc.new_page()
    y = 72.0
    for _ in range(3):
        p1.insert_text((72, y), _PREENCHIMENTO, fontsize=11)
        y += 16
    p2 = doc.new_page()
    y = 72.0
    p2.insert_text((72, y), _PREENCHIMENTO[:60], fontsize=11)
    y += 16
    p2.insert_text((72, y), _PREENCHIMENTO[60:], fontsize=11)
    y += 24
    p2.insert_text((72, y), "Anotacao relevante", fontsize=11, fontname="Helvetica-Bold")
    b = doc.tobytes()
    doc.close()
    return b


def _pdf_wide_table_rule_false_positive() -> bytes:
    """🔴 The `trt2_fisico` production defect, reproduced synthetically: a
    table/box rule far wider than the short text it happens to run under,
    sitting exactly inside the underline geometry window. It overlaps the
    digits by 100% and passes the OLD (span-width-only) check — it must
    NOT be read as an underline once the line-width guard is in place."""
    doc = fitz.open()
    page = doc.new_page()
    y = 72.0
    page.insert_text((72, y), _PREENCHIMENTO, fontsize=11)
    y += 20
    baseline = y
    page.insert_text((72, y), "12345", fontsize=10, fontname="Courier")
    # A rule crossing far more than the "12345" line's own width.
    page.draw_line((40, baseline + 1.5), (540, baseline + 1.5), width=0.7)
    b = doc.tobytes()
    doc.close()
    return b


def _pdf_scanned_page() -> bytes:
    """A page with an embedded raster image and NO extractable text —
    `classify_pdf_text_layer` must route it to vision."""
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10))
    pix.set_rect(pix.irect, (180, 180, 180))
    page.insert_image(fitz.Rect(72, 72, 300, 300), pixmap=pix)
    b = doc.tobytes()
    doc.close()
    return b


def _texto_bruto_pagina(pdf_bytes: bytes, index: int = 0) -> str:
    """Independent oracle: PyMuPDF's own plain-text extraction, computed
    WITHOUT going through this module at all — what `page.text` must equal
    for the byte-identity proof to mean anything."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return doc[index].get_text().strip()
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Rung 1 — text layer: byte-identity of `page.text`
# ---------------------------------------------------------------------------


class TestPageTextStaysByteIdentical:
    """🔴 The invariant this whole feature is not allowed to break: existing
    consumers (matrícula acts, migration 109) store offsets into `page.text`
    — formatting must sit ALONGSIDE it, never inside it."""

    @pytest.mark.parametrize(
        "builder",
        [
            _pdf_plain_only,
            _pdf_bold_and_underline,
            _pdf_bold_and_underline_combined,
            _pdf_wide_table_rule_false_positive,
        ],
    )
    @pytest.mark.asyncio
    async def test_text_is_unchanged_by_formatting_extraction(self, builder) -> None:
        pdf_bytes = builder()
        esperado = _texto_bruto_pagina(pdf_bytes)

        t = LadderDocumentTranscriber()
        out = await t.transcribe(pdf_bytes)

        assert out.ok, out.error_message
        assert len(out.pages) == 1
        assert out.pages[0].text == esperado
        assert out.pages[0].source is TextSource.TEXT_LAYER

    @pytest.mark.asyncio
    async def test_multi_page_text_is_unchanged(self) -> None:
        pdf_bytes = _pdf_multi_page_mixed()
        esperado_p1 = _texto_bruto_pagina(pdf_bytes, 0)
        esperado_p2 = _texto_bruto_pagina(pdf_bytes, 1)

        out = await LadderDocumentTranscriber().transcribe(pdf_bytes)

        assert out.ok, out.error_message
        assert [p.text for p in out.pages] == [esperado_p1, esperado_p2]


# ---------------------------------------------------------------------------
# Rung 1 — bold + underline detection
# ---------------------------------------------------------------------------


class TestTextLayerFormattingDetection:
    @pytest.mark.asyncio
    async def test_a_bold_line_is_captured(self) -> None:
        pdf_bytes = _pdf_bold_and_underline()
        out = await LadderDocumentTranscriber().transcribe(pdf_bytes)

        pagina = out.pages[0]
        negritos = [r for r in pagina.formatting if r.bold and not r.underline]
        assert len(negritos) == 1
        r = negritos[0]
        assert pagina.text[r.start : r.end] == "Titular do dominio"

    @pytest.mark.asyncio
    async def test_an_underlined_line_is_captured(self) -> None:
        pdf_bytes = _pdf_bold_and_underline()
        out = await LadderDocumentTranscriber().transcribe(pdf_bytes)

        pagina = out.pages[0]
        sublinhados = [r for r in pagina.formatting if r.underline and not r.bold]
        assert len(sublinhados) == 1
        r = sublinhados[0]
        assert pagina.text[r.start : r.end] == "Onus e gravames vigentes"

    @pytest.mark.asyncio
    async def test_bold_and_underline_combine_on_one_range(self) -> None:
        pdf_bytes = _pdf_bold_and_underline_combined()
        out = await LadderDocumentTranscriber().transcribe(pdf_bytes)

        pagina = out.pages[0]
        combinados = [r for r in pagina.formatting if r.bold and r.underline]
        assert len(combinados) == 1
        r = combinados[0]
        assert pagina.text[r.start : r.end] == "Averbacao de onus real"

    @pytest.mark.asyncio
    async def test_plain_text_carries_no_formatting(self) -> None:
        out = await LadderDocumentTranscriber().transcribe(_pdf_plain_only())
        assert out.pages[0].formatting == ()

    def test_every_range_reconstructs_the_exact_substring(self) -> None:
        """The strongest possible offset assertion: slicing `text` at every
        range's `[start, end)` reproduces exactly the formatted word(s), for
        every range this module produces — no manual offset arithmetic to
        get wrong in the test itself."""
        pdf_bytes = _pdf_bold_and_underline()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            texto = doc[0].get_text().strip()
            ranges = _extract_text_layer_formatting(doc[0], texto)
        finally:
            doc.close()
        assert ranges
        for r in ranges:
            trecho = texto[r.start : r.end]
            assert trecho.strip() == trecho, "a range must not include padding whitespace"
            assert trecho, "a FormatRange must never cover empty text"


# ---------------------------------------------------------------------------
# Rung 1 — the `trt2_fisico` production false positive, reproduced
# ---------------------------------------------------------------------------


class TestWideTableRuleIsNotAnUnderline:
    """🔴 Real production defect (2026-09-14 sample pass): a table/box rule
    82-229x wider than the digits it ran through was read as an underline
    by geometry alone, on a real certidão template (`trt2_fisico`, 36 false
    hits). Reproduced synthetically here — no real document content."""

    @pytest.mark.asyncio
    async def test_a_wide_table_rule_under_short_text_is_not_underlined(self) -> None:
        pdf_bytes = _pdf_wide_table_rule_false_positive()
        out = await LadderDocumentTranscriber().transcribe(pdf_bytes)

        assert out.ok, out.error_message
        pagina = out.pages[0]
        assert "12345" in pagina.text
        assert pagina.formatting == (), (
            "a table rule far wider than its line must not become an "
            "underline range"
        )


# ---------------------------------------------------------------------------
# Rung 1 — alignment failure is a silent drop, never a text shift
# ---------------------------------------------------------------------------


class _FakePage:
    """A minimal page double exposing exactly the two PyMuPDF calls
    `_extract_text_layer_formatting` uses. Not a patch of this module's own
    code — a plain stand-in object passed as an ordinary argument."""

    def __init__(self, spans: list[dict], drawings: tuple = ()) -> None:
        self._spans = spans
        self._drawings = drawings

    def get_text(self, mode: str = "text"):
        assert mode == "dict"
        return {"blocks": [{"lines": [{"spans": self._spans}]}]}

    def get_drawings(self):
        return self._drawings


class TestUnalignableSpansAreDroppedNotGuessed:
    def test_a_span_absent_from_the_text_is_dropped(self) -> None:
        pagina = _FakePage(
            spans=[
                {
                    "text": "texto que nao existe na pagina",
                    "flags": 16,
                    "font": "Helvetica-Bold",
                    "bbox": (0, 0, 10, 10),
                    "origin": (0, 10),
                    "size": 10,
                }
            ]
        )
        ranges = _extract_text_layer_formatting(pagina, text="Algo completamente diferente")
        assert ranges == ()

    def test_a_whitespace_only_span_is_skipped(self) -> None:
        pagina = _FakePage(
            spans=[
                {
                    "text": "   ",
                    "flags": 16,
                    "font": "Helvetica-Bold",
                    "bbox": (0, 0, 10, 10),
                    "origin": (0, 10),
                    "size": 10,
                }
            ]
        )
        assert _extract_text_layer_formatting(pagina, text="qualquer texto") == ()


class TestBoldDetection:
    def test_the_pymupdf_bold_flag_is_enough(self) -> None:
        assert _is_bold_span({"flags": 16, "font": "Helvetica"}) is True

    @pytest.mark.parametrize("marcador", ["Bold", "Black", "Heavy", "Semibold"])
    def test_a_bold_family_font_name_counts_even_without_the_flag(self, marcador) -> None:
        assert _is_bold_span({"flags": 0, "font": f"CustomFont-{marcador}"}) is True

    def test_neither_signal_is_not_bold(self) -> None:
        assert _is_bold_span({"flags": 0, "font": "Helvetica"}) is False


class TestUnderlineDetection:
    def _span(self, x0=100, x1=140, size=11) -> dict:
        baseline = 200.0
        return {"bbox": (x0, baseline - size, x1, baseline + 3), "origin": (x0, baseline), "size": size}

    def test_a_line_just_below_the_baseline_counts(self) -> None:
        span = self._span()
        assert _has_underline(span, 40, [(100, 140, 201.0)]) is True

    def test_a_line_far_below_the_baseline_does_not_count(self) -> None:
        span = self._span()
        assert _has_underline(span, 40, [(100, 140, 220.0)]) is False

    def test_a_line_that_barely_overlaps_the_span_does_not_count(self) -> None:
        span = self._span(x0=100, x1=140)  # width 40
        # Only 10 of 40 points overlap — below the 50% threshold.
        assert _has_underline(span, 40, [(130, 140, 201.0)]) is False

    def test_no_drawings_at_all_is_not_underlined(self) -> None:
        assert _has_underline(self._span(), 40, []) is False

    def test_a_table_rule_far_wider_than_the_line_does_not_count(self) -> None:
        """🔴 The `trt2_fisico` false positive: a table/box rule ran clean
        through a short Courier digit run, overlapping it by 100% and
        sitting exactly in the underline window — and was NOT an underline.
        The fix is comparing the segment's length against the LINE's own
        width, not just the individual span's."""
        span = self._span(x0=100, x1=110)  # a narrow span, e.g. one digit
        linha_largura = 12  # the line is barely wider than the span itself
        regua_larga = (0, 900, 201.0)  # an 82x-wider table rule
        assert _has_underline(span, linha_largura, [regua_larga]) is False

    def test_a_rule_comparable_to_the_line_width_still_counts(self) -> None:
        """The guard must not reject an ordinary underline that happens to
        run slightly past its own span into the rest of a short line."""
        span = self._span(x0=100, x1=140)
        linha_largura = 45  # the underlined word is almost the whole line
        assert _has_underline(span, linha_largura, [(100, 145, 201.0)]) is True


class TestMergeAdjacentRanges:
    def test_touching_same_formatting_ranges_merge(self) -> None:
        merged = _merge_adjacent_ranges(
            [
                FormatRange(start=0, end=5, bold=True),
                FormatRange(start=5, end=10, bold=True),
            ]
        )
        assert merged == (FormatRange(start=0, end=10, bold=True),)

    def test_a_gap_prevents_merging(self) -> None:
        merged = _merge_adjacent_ranges(
            [
                FormatRange(start=0, end=5, bold=True),
                FormatRange(start=6, end=10, bold=True),
            ]
        )
        assert len(merged) == 2

    def test_different_formatting_does_not_merge(self) -> None:
        merged = _merge_adjacent_ranges(
            [
                FormatRange(start=0, end=5, bold=True),
                FormatRange(start=5, end=10, underline=True),
            ]
        )
        assert len(merged) == 2


# ---------------------------------------------------------------------------
# Rung 2 — the vision markup parser, as a pure function
# ---------------------------------------------------------------------------


class TestParseMarkupBasics:
    def test_plain_text_with_no_markers_passes_through(self) -> None:
        assert parse_markup("nenhuma marcacao aqui") == ("nenhuma marcacao aqui", ())

    def test_bold_marker(self) -> None:
        texto, ranges = parse_markup("um **termo em negrito** qualquer")
        assert texto == "um termo em negrito qualquer"
        assert ranges == (FormatRange(start=3, end=19, bold=True),)

    def test_underline_marker(self) -> None:
        texto, ranges = parse_markup("um <u>termo sublinhado</u> qualquer")
        assert texto == "um termo sublinhado qualquer"
        assert ranges == (FormatRange(start=3, end=19, underline=True),)

    @pytest.mark.parametrize(
        "marcado",
        ["<u>**negrito e sublinhado**</u>", "**<u>negrito e sublinhado</u>**"],
    )
    def test_nesting_in_either_order_combines_both(self, marcado) -> None:
        texto, ranges = parse_markup(marcado)
        assert texto == "negrito e sublinhado"
        assert ranges == (FormatRange(start=0, end=20, bold=True, underline=True),)

    def test_adjacent_runs_stay_separate_ranges(self) -> None:
        texto, ranges = parse_markup("**bold** <u>under</u>")
        assert texto == "bold under"
        assert ranges == (
            FormatRange(start=0, end=4, bold=True),
            FormatRange(start=5, end=10, underline=True),
        )

    def test_markers_at_the_very_start_and_end_of_the_string(self) -> None:
        texto, ranges = parse_markup("**start**\nmiddle\n**end**")
        assert texto == "start\nmiddle\nend"
        assert ranges == (
            FormatRange(start=0, end=5, bold=True),
            FormatRange(start=13, end=16, bold=True),
        )


class TestParseMarkupNeverRaisesOnMalformedInput:
    """The vision model is not a compiler — its reply can be anything, and
    this parser must always return a usable document instead."""

    def test_lone_literal_asterisks_are_not_markers(self) -> None:
        """`* * *` (single, space-separated asterisks) is a real ABNT
        registry idiom (a redaction placeholder), not a `**` pair — it must
        never be interpreted as an unterminated bold toggle."""
        texto, ranges = parse_markup("R.1 * * *")
        assert texto == "R.1 * * *"
        assert ranges == ()

    def test_empty_markers_produce_no_text_and_no_range(self) -> None:
        texto, ranges = parse_markup("antes ****depois")
        assert texto == "antes depois"
        assert ranges == ()

    def test_an_unbalanced_bold_marker_stays_literal(self) -> None:
        texto, ranges = parse_markup("primeiro **fechado** mas **nunca fecha")
        assert texto == "primeiro fechado mas **nunca fecha"
        assert ranges == (FormatRange(start=9, end=16, bold=True),)

    def test_a_stray_closing_underline_tag_stays_literal(self) -> None:
        texto, ranges = parse_markup("fecha </u> sem abrir")
        assert texto == "fecha </u> sem abrir"
        assert ranges == ()

    def test_an_unclosed_opening_underline_tag_stays_literal(self) -> None:
        texto, ranges = parse_markup("abre <u> mas nunca fecha")
        assert texto == "abre <u> mas nunca fecha"
        assert ranges == ()

    def test_an_unknown_tag_stays_literal(self) -> None:
        texto, ranges = parse_markup("nao pedimos <i>italico</i> aqui")
        assert texto == "nao pedimos <i>italico</i> aqui"
        assert ranges == ()

    def test_an_unknown_tag_is_logged(self, caplog) -> None:
        with caplog.at_level("WARNING"):
            parse_markup("<i>italico</i>")
        assert any("<i>" in m for m in caplog.messages)

    @pytest.mark.parametrize(
        "marcado",
        [
            "",
            "**",
            "<u>",
            "</u>",
            "****<u></u>****",
            "*<u>*</u>*",
            "**<u>**</u>**",
            "\n\n**\n<u>\n",
            "a" * 500 + "**" + "b" * 500,
        ],
    )
    def test_never_raises_on_adversarial_input(self, marcado) -> None:
        texto, ranges = parse_markup(marcado)
        assert isinstance(texto, str)
        for r in ranges:
            assert 0 <= r.start < r.end <= len(texto)
            assert r.bold or r.underline


class TestOnePromptConstantForEveryProvider:
    """`OCR_PROMPT` asks for the markup, and it must reach every vendor
    identically — `parse_markup` only knows how to read the markers this
    exact prompt asks for."""

    @pytest.mark.parametrize("provider,model", [
        ("openai", "gpt-4.1-mini"),
        ("anthropic", "claude-opus-5"),
        ("gemini", "gemini-2.0-flash"),
    ])
    @pytest.mark.asyncio
    async def test_the_same_prompt_reaches_every_vendor(
        self, monkeypatch, provider, model
    ) -> None:
        import noctusai_lib.integrations.documents.transcription as mod

        prompts: list[str] = []

        async def recorder(image, prompt, *, model=None, provider=None, org_id=None, max_tokens=None):
            prompts.append(prompt)
            return "OCR SEM MARCACAO"

        monkeypatch.setattr(mod, "_contar_paginas", lambda b: 1)
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer",
            lambda b: classify_pdf_text_layer(b"") ,
        )
        monkeypatch.setattr(mod, "_pdf_to_images", lambda b, paginas, dpi: {1: b"png"})

        t = LadderDocumentTranscriber(analyze=recorder, provider=provider)
        await t.transcribe(b"%PDF")

        assert prompts == [OCR_PROMPT]


# ---------------------------------------------------------------------------
# Rung 2 — end to end through LadderDocumentTranscriber
# ---------------------------------------------------------------------------


class TestVisionRungEndToEnd:
    """A real scanned page (no text layer, one embedded image) routed
    through the fake vision provider — the seam `LadderDocumentTranscriber`
    already offers via `analyze=`, not a patch of the class under test."""

    @pytest.mark.asyncio
    async def test_a_scanned_page_is_parsed_from_its_markup(self) -> None:
        async def fake_vision(image, prompt, *, model=None, provider=None, org_id=None, max_tokens=None):
            return (
                "Certifico que consta **regularmente registrado** o imovel, "
                "com <u>onus real vigente</u> anotado a margem."
            )

        pdf_bytes = _pdf_scanned_page()
        out = await LadderDocumentTranscriber(analyze=fake_vision).transcribe(pdf_bytes)

        assert out.ok, out.error_message
        pagina = out.pages[0]
        assert pagina.source is TextSource.OCR
        assert "**" not in pagina.text and "<u>" not in pagina.text
        negrito = [r for r in pagina.formatting if r.bold]
        sublinhado = [r for r in pagina.formatting if r.underline]
        assert len(negrito) == 1
        assert pagina.text[negrito[0].start : negrito[0].end] == "regularmente registrado"
        assert len(sublinhado) == 1
        assert pagina.text[sublinhado[0].start : sublinhado[0].end] == "onus real vigente"

    @pytest.mark.asyncio
    async def test_a_malformed_vision_reply_still_yields_a_document(self) -> None:
        """The parser never raises — a background transcription job must
        not die because the model's reply had one stray marker."""
        async def fake_vision(image, prompt, *, model=None, provider=None, org_id=None, max_tokens=None):
            return "Texto com marcador **sem fechar corretamente"

        out = await LadderDocumentTranscriber(analyze=fake_vision).transcribe(
            _pdf_scanned_page()
        )

        assert out.ok, out.error_message
        assert out.pages[0].text == "Texto com marcador **sem fechar corretamente"
        assert out.pages[0].formatting == ()

    @pytest.mark.asyncio
    async def test_document_level_formatting_rebases_across_pages(self) -> None:
        """`Transcription.formatting` must use the exact "\\n\\n" join
        `Transcription.text` uses — checked here by RECONSTRUCTING each
        range's substring straight out of `out.text`, not by hand-deriving
        the expected offsets."""
        pdf_bytes = _pdf_multi_page_mixed()

        out = await LadderDocumentTranscriber().transcribe(pdf_bytes)

        assert out.ok, out.error_message
        assert len(out.pages) == 2
        assert out.pages[1].formatting, "fixture must carry a bold line on page 2"
        assert out.formatting, "document-level formatting must not be empty"
        for r in out.formatting:
            trecho = out.text[r.start : r.end]
            assert trecho == "Anotacao relevante"
