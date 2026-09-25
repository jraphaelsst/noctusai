"""`paginas=` — the new seed page-targeting capability, on BOTH
`DocumentTranscriber.transcribe` (`transcription.py`) and
`DocumentTextLadder.to_text` (`ladder.py`). See the negociação/
financiamento extraction contract §D.4.

PyMuPDF is stubbed out (same convention `test_transcription.py` uses): what
these tests defend is the PAGE-ELIGIBILITY routing, and real bytes would
make each case an exercise in PDF construction instead.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
from noctusai_lib.integrations.documents.transcription import (
    LadderDocumentTranscriber,
    Transcription,
    TranscribedPage,
)
from noctusai_lib.integrations.documents.types import TextSource
from noctusai_lib.integrations.media import PdfPage, PdfTextLayer


def _camada(*paginas: tuple[str, bool]) -> PdfTextLayer:
    return PdfTextLayer(
        pages=tuple(
            PdfPage(number=i, text=t, is_substantive=sub, reason="stub")
            for i, (t, sub) in enumerate(paginas, 1)
        ),
        tooling_available=True,
    )


def _vision_for():
    """A vision stub whose text output NAMES the real page number it was
    billed for (`_pdf_to_images` below hands it that page's own bytes as a
    tag), so a test can assert exactly which pages were visioned without
    depending on call order."""
    billed: list[int] = []

    async def analyze(image, prompt, *, model=None, provider=None, org_id=None, max_tokens=None):
        pagina = int(image.decode())
        billed.append(pagina)
        return f"OCR PAGINA {pagina}"

    analyze.billed = billed  # type: ignore[attr-defined]
    return analyze


def _transcriber(monkeypatch, camada, *, num_paginas, vision=None, **kw):
    """Wire a Ladder transcriber over stubbed PDF mechanics — same helper
    `test_transcription.py` uses. `_pdf_to_images` returns each requested
    page's OWN number, encoded, as its "image" bytes, so the vision stub
    can report exactly which page it was billed for."""
    import noctusai_lib.integrations.documents.transcription as mod

    monkeypatch.setattr(mod, "_contar_paginas", lambda b: num_paginas)
    monkeypatch.setattr(
        "noctusai_lib.integrations.media.classify_pdf_text_layer", lambda b: camada
    )
    monkeypatch.setattr(
        mod,
        "_pdf_to_images",
        lambda b, paginas, dpi: {n: str(n).encode() for n in paginas},
    )
    return LadderDocumentTranscriber(analyze=vision or _vision_for(), **kw)


class TestDefaultIsByteForByteUnchanged:
    """`paginas=None` — every existing behaviour, untouched."""

    @pytest.mark.asyncio
    async def test_a_mixed_document_reads_exactly_as_before(self, monkeypatch):
        camada = _camada(
            ("PAGINA 1 TEXTO REAL", True), ("", False), ("PAGINA 3 TEXTO REAL", True)
        )
        vision = _vision_for()
        t = _transcriber(monkeypatch, camada, num_paginas=3, vision=vision)

        r = await t.transcribe(b"pdf", paginas=None)
        assert r.ok
        assert [p.number for p in r.pages] == [1, 2, 3]
        assert vision.billed == [2]
        assert r.paginas_por_camada == (1, 3)
        assert r.paginas_por_visao == (2,)

    @pytest.mark.asyncio
    async def test_no_paginas_argument_at_all_matches_paginas_none(self, monkeypatch):
        camada = _camada(("PAGINA 1", True), ("PAGINA 2", True))
        t = _transcriber(monkeypatch, camada, num_paginas=2)

        r_default = await t.transcribe(b"pdf")
        r_explicit_none = await t.transcribe(b"pdf", paginas=None)
        assert [p.number for p in r_default.pages] == [p.number for p in r_explicit_none.pages]

    @pytest.mark.asyncio
    async def test_too_many_vision_pages_still_fires_over_the_whole_document(self, monkeypatch):
        camada = _camada(*[("", False)] * 5)
        t = _transcriber(monkeypatch, camada, num_paginas=5, max_vision_pages=2)

        r = await t.transcribe(b"pdf")
        assert r.error == "too_many_vision_pages"


class TestPaginasNarrowsTheEligibleSet:
    @pytest.mark.asyncio
    async def test_pages_outside_paginas_never_appear_in_the_output(self, monkeypatch):
        camada = _camada(
            ("PAGINA 1", True), ("PAGINA 2", True), ("PAGINA 3", True), ("PAGINA 4", True)
        )
        t = _transcriber(monkeypatch, camada, num_paginas=4)

        r = await t.transcribe(b"pdf", paginas=[2, 3])
        assert [p.number for p in r.pages] == [2, 3]
        assert 1 not in [p.number for p in r.pages]
        assert 4 not in [p.number for p in r.pages]

    @pytest.mark.asyncio
    async def test_paginas_never_visions_an_ineligible_page(self, monkeypatch):
        """A page NEEDING vision, but outside `paginas`, must never be
        rasterized/billed — the central `paginas=` guarantee."""
        camada = _camada(("", False), ("", False), ("", False))  # every page scanned
        vision = _vision_for()
        t = _transcriber(monkeypatch, camada, num_paginas=3, vision=vision)

        r = await t.transcribe(b"pdf", paginas=[1])
        assert vision.billed == [1]
        assert 2 not in vision.billed
        assert 3 not in vision.billed
        assert [p.number for p in r.pages] == [1]

    @pytest.mark.asyncio
    async def test_num_paginas_still_reports_the_whole_document(self, monkeypatch):
        camada = _camada(*[("PAGINA", True)] * 10)
        t = _transcriber(monkeypatch, camada, num_paginas=10)

        r = await t.transcribe(b"pdf", paginas=[1, 2])
        assert r.num_paginas == 10
        assert len(r.pages) == 2

    @pytest.mark.asyncio
    async def test_out_of_range_page_numbers_are_dropped_not_an_error(self, monkeypatch):
        camada = _camada(("PAGINA 1", True), ("PAGINA 2", True))
        t = _transcriber(monkeypatch, camada, num_paginas=2)

        r = await t.transcribe(b"pdf", paginas=[1, 99])
        assert r.ok
        assert [p.number for p in r.pages] == [1]

    @pytest.mark.asyncio
    async def test_a_window_entirely_out_of_range_is_empty_not_an_error(self, monkeypatch):
        camada = _camada(("PAGINA 1", True), ("PAGINA 2", True))
        t = _transcriber(monkeypatch, camada, num_paginas=2)

        r = await t.transcribe(b"pdf", paginas=[50, 51])
        assert r.ok
        assert r.pages == ()
        assert r.error is None

    @pytest.mark.asyncio
    async def test_too_many_vision_pages_is_judged_against_the_eligible_set_only(
        self, monkeypatch
    ):
        """25 pages all need vision; `max_vision_pages` is BELOW the whole
        document but ABOVE one 4-page window — the cap must never fire
        just because the WHOLE document is large."""
        camada = _camada(*[("", False)] * 25)
        t = _transcriber(monkeypatch, camada, num_paginas=25, max_vision_pages=4)

        r = await t.transcribe(b"pdf", paginas=range(1, 5))
        assert r.error is None
        assert len(r.pages) == 4

    @pytest.mark.asyncio
    async def test_force_vision_sends_every_eligible_page_to_vision(self, monkeypatch):
        # Every page has substantive text (rung 1 would normally answer
        # for free) — `force_vision=True` must still vision every ELIGIBLE
        # page, and none outside `paginas`.
        camada = _camada(("PAGINA 1", True), ("PAGINA 2", True), ("PAGINA 3", True))
        vision = _vision_for()
        t = _transcriber(monkeypatch, camada, num_paginas=3, vision=vision)

        r = await t.transcribe(b"pdf", paginas=[1, 2], force_vision=True)
        assert sorted(vision.billed) == [1, 2]
        assert r.paginas_por_visao == (1, 2)


class TestContractTwoPassWindow:
    """The 25-page all-vision case: window 4, two passes, ≤8 vision calls,
    never `too_many_vision_pages` — the exact shape
    `financiamento_imobiliario.LadderContratoFinanciamentoExtractor` uses."""

    @pytest.mark.asyncio
    async def test_two_windows_of_four_cost_at_most_eight_vision_calls(self, monkeypatch):
        camada = _camada(*[("", False)] * 25)  # every page image-only
        vision = _vision_for()
        t = _transcriber(monkeypatch, camada, num_paginas=25, vision=vision, max_vision_pages=40)

        r1 = await t.transcribe(b"pdf", paginas=range(1, 5))
        r2 = await t.transcribe(b"pdf", paginas=range(5, 9))

        assert r1.error is None and r2.error is None
        assert len(vision.billed) <= 8
        assert sorted(vision.billed) == [1, 2, 3, 4, 5, 6, 7, 8]

    @pytest.mark.asyncio
    async def test_never_returns_too_many_vision_pages_across_either_window(self, monkeypatch):
        camada = _camada(*[("", False)] * 25)
        # A cap that WOULD trip on the whole 25-page document, but never on
        # a single 4-page window.
        t = _transcriber(monkeypatch, camada, num_paginas=25, max_vision_pages=8)

        for janela in (range(1, 5), range(5, 9)):
            r = await t.transcribe(b"pdf", paginas=janela)
            assert r.error != "too_many_vision_pages"


class TestDocumentTextLadderPaginas:
    """`DocumentTextLadder.to_text(paginas=...)` — rung 1 restricted to the
    eligible window; rung 2 bypasses the whole-document media resolver via
    an injected `document_transcriber=` (see `ladder._get_document_transcriber`)."""

    @pytest.mark.asyncio
    async def test_default_paginas_none_goes_through_the_whole_document_resolver(
        self, monkeypatch
    ):
        calls = []

        class _StubResolver:
            async def resolve(self, media):
                calls.append(media)

                class _R:
                    text = "resolved text"
                    error = None

                return _R()

        ladder = DocumentTextLadder(resolver=_StubResolver())
        text, source, err = await ladder.to_text(b"img", mimetype="image/jpeg")
        assert text == "resolved text"
        assert source == TextSource.OCR
        assert err is None
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_paginas_all_substantive_window_is_free_text_layer(self, monkeypatch):
        camada = _camada(("PAGINA 1", True), ("PAGINA 2", True), ("PAGINA 3", True))
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer", lambda b: camada
        )

        class _NeverCalled:
            async def transcribe(self, *a, **kw):
                raise AssertionError("rung 2 must not be reached")

        ladder = DocumentTextLadder(document_transcriber=_NeverCalled())
        text, source, err = await ladder.to_text(
            b"pdf", mimetype="application/pdf", paginas=[1, 2]
        )
        assert source == TextSource.TEXT_LAYER
        assert "PAGINA 1" in text and "PAGINA 2" in text
        assert "PAGINA 3" not in text
        assert err is None

    @pytest.mark.asyncio
    async def test_partial_substantive_window_bypasses_to_the_transcriber(self, monkeypatch):
        camada = _camada(("PAGINA 1", True), ("", False))
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer", lambda b: camada
        )

        class _Stub:
            async def transcribe(self, content, *, mimetype=None, filename=None, force_vision=False, paginas=None):
                assert list(paginas) == [1, 2]
                return Transcription(
                    pages=(
                        TranscribedPage(number=1, text="PAGINA 1", source=TextSource.TEXT_LAYER),
                        TranscribedPage(number=2, text="PAGINA 2 OCR", source=TextSource.OCR),
                    ),
                    num_paginas=2,
                )

        ladder = DocumentTextLadder(document_transcriber=_Stub())
        text, source, err = await ladder.to_text(
            b"pdf", mimetype="application/pdf", paginas=[1, 2]
        )
        assert source == TextSource.OCR  # at least one page cost a vision call
        assert "PAGINA 1" in text and "PAGINA 2 OCR" in text
        assert err is None

    @pytest.mark.asyncio
    async def test_transcriber_error_is_surfaced(self, monkeypatch):
        camada = _camada(("", False),)
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer", lambda b: camada
        )

        class _Failing:
            async def transcribe(self, *a, **kw):
                return Transcription(error="missing_credentials", error_message="no key")

        ladder = DocumentTextLadder(document_transcriber=_Failing())
        text, source, err = await ladder.to_text(
            b"pdf", mimetype="application/pdf", paginas=[1]
        )
        assert text == ""
        assert source == TextSource.NENHUMA
        assert err == ("missing_credentials", "no key")

    @pytest.mark.asyncio
    async def test_empty_window_is_nenhuma_not_an_error(self, monkeypatch):
        camada = _camada(("PAGINA 1", True),)
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer", lambda b: camada
        )

        class _Stub:
            async def transcribe(self, *a, **kw):
                return Transcription(pages=(), num_paginas=1)

        ladder = DocumentTextLadder(document_transcriber=_Stub())
        text, source, err = await ladder.to_text(
            b"pdf", mimetype="application/pdf", paginas=[50]
        )
        assert text == ""
        assert source == TextSource.NENHUMA
        assert err is None

    @pytest.mark.asyncio
    async def test_paginas_is_ignored_for_non_pdf_media(self, monkeypatch):
        """An image has no page concept — `paginas=` must be a no-op and
        the normal whole-document resolver path still runs."""
        calls = []

        class _StubResolver:
            async def resolve(self, media):
                calls.append(media)

                class _R:
                    text = "image text"
                    error = None

                return _R()

        class _NeverCalled:
            async def transcribe(self, *a, **kw):
                raise AssertionError("a non-PDF must never reach the page-targeted rung")

        ladder = DocumentTextLadder(resolver=_StubResolver(), document_transcriber=_NeverCalled())
        text, source, err = await ladder.to_text(
            b"img", mimetype="image/jpeg", paginas=[1]
        )
        assert text == "image text"
        assert len(calls) == 1
