"""Tests for the public `extract_pdf_text(...)` helper (lifted
2026-05-19 from social-wiring `media_service._extract_pdf_text`,
single-sourced with `OpenAIMediaResolver._pdf_text_layer`)."""

from __future__ import annotations

import builtins

import pytest

from noctusai_lib.integrations.media import (
    classify_pdf_text_layer,
    strip_provenance_stamps,
    extract_pdf_text,
    pdf_text_tooling_available,
)
from noctusai_lib.integrations.media.pdf_text import _extract_pdf_text_with_signal


class TestExtractPdfTextDegraded:
    def test_empty_bytes_returns_empty(self) -> None:
        assert extract_pdf_text(b"") == ""

    def test_garbage_bytes_returns_empty(self) -> None:
        # Neither PyMuPDF nor pdfminer should crash on garbage; they
        # may log + return empty.
        result = extract_pdf_text(b"not a pdf at all\x00\x01\x02")
        assert result == ""

    def test_no_libs_available_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With neither PyMuPDF nor pdfminer importable, the helper
        returns `""` (NOT crash) and `pdf_text_tooling_available()`
        reports False."""
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[override]
            if name in ("fitz", "pdfminer", "pdfminer.high_level"):
                raise ImportError("simulated slim env")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert pdf_text_tooling_available() is False
        assert extract_pdf_text(b"%PDF-fake") == ""


class TestExtractPdfTextWithSignal:
    def test_signal_distinguishes_no_tooling(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[override]
            if name in ("fitz", "pdfminer", "pdfminer.high_level"):
                raise ImportError("simulated")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        text, available = _extract_pdf_text_with_signal(b"%PDF-x")
        assert text == ""
        assert available is False


# ---------------------------------------------------------------------------
# classify_pdf_text_layer — is this text layer CONTENT, or a stamp on a scan?
# ---------------------------------------------------------------------------

def _pdf(pages: list[tuple[str, bool]]) -> bytes:
    """Build a PDF where each page carries `text` and, when `scanned`, a
    page-sized raster image underneath it — the shape a cartório issues."""
    fitz = pytest.importorskip("fitz")

    doc = fitz.open()
    for text, scanned in pages:
        page = doc.new_page()
        if scanned:
            # A page-sized JPEG is what makes a scan a scan. The pixmap is
            # solid grey; only its dimensions matter to the classifier.
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 280))
            pix.set_rect(pix.irect, (128, 128, 128))
            page.insert_image(page.rect, pixmap=pix)
        if text:
            page.insert_textbox(
                fitz.Rect(20, 20, page.rect.width - 20, page.rect.height - 20),
                text,
                fontsize=6,
            )
    out = doc.tobytes()
    doc.close()
    return out


#: The real stamp from the 2026-08-25 ERP defect — 137 characters that
#: cleared every "does this PDF have a text layer?" check on the platform.
#: Verbatim from `CERTIDÃO DE MATRÍCULA - EUROVILLE.pdf` and
#: `MATRICULA CANTAGALO.pdf`, both ingested by this platform.
ONR_STAMP = (
    "Valide este documento clicando no link a seguir: "
    "https://assinador-web.onr.org.br/docs/7JX9U-HLZEA-9LJWT-PM2QS\n"
    "Valide aqui\neste documento"
)

#: The OTHER ONR stamp — 83 characters, printed on a "Visualização de
#: Matrícula" instead of a "Certidão". Verbatim from
#: `Visualização de Matrícula - Quebec - Casa 78.pdf`.
#:
#: 🔴 THE TWO STAMPS ARE WHY THIS FILE HAS A REGRESSION TEST.
#: 137 and 83 sit on opposite sides of `MIN_CHARS_PER_PAGE` (100), so the
#: character floor accepted one document type and rejected the other — a
#: certidão silently transcribed as its own validation link while a
#: visualização went to vision and came back whole. The difference was
#: never a property of the documents.
ONR_VISUALIZACAO_STAMP = (
    "SOLICITADO POR: GILSON JUNIOR - CPF/CNPJ: ***.751.658-** "
    "DATA:  25/08/2026 10:23:01"
)


class TestStripProvenanceStamps:
    """The stamps carry provenance, never content — so removing them can
    never remove anything the document says."""

    def test_both_real_onr_stamps_strip_to_nothing(self) -> None:
        assert strip_provenance_stamps(ONR_STAMP) == ""
        assert strip_provenance_stamps(ONR_VISUALIZACAO_STAMP) == ""

    def test_the_stamps_straddle_the_char_floor(self) -> None:
        """The measurement that explains the whole defect, pinned so it
        cannot be re-derived wrongly: 137 > 100 >= 83."""
        assert len(ONR_STAMP) == 137
        assert len(ONR_VISUALIZACAO_STAMP) == 83

    def test_real_prose_survives_untouched(self) -> None:
        """A pattern that ate content would be far worse than the defect
        it fixes — `find_matricula` reads whatever survives this pass."""
        corpo = (
            "CERTIFICO E DOU FÉ que esta certidão foi extraída em inteiro teor,\n"
            "do imóvel da matrícula n.º 124.086, e que nos arquivos desta\n"
            "Serventia não há registro de quaisquer ALIENAÇÕES."
        )
        assert strip_provenance_stamps(corpo) == corpo

    def test_a_stamp_wrapped_into_content_only_loses_the_stamp(self) -> None:
        misto = f"{ONR_STAMP}\nIMÓVEL: Terreno situado na Alameda Alemanha."
        assert strip_provenance_stamps(misto) == (
            "IMÓVEL: Terreno situado na Alameda Alemanha."
        )

    def test_accents_and_case_do_not_defeat_the_match(self) -> None:
        """Extraction drops accents and re-cases text often enough that
        matching on the literal would be a coin flip."""
        assert strip_provenance_stamps("VALIDE ESTE DOCUMENTO CLICANDO NO LINK") == ""
        assert strip_provenance_stamps("Solicitado por: FULANO - CPF: x") == ""

    def test_empty_input_is_empty_output(self) -> None:
        assert strip_provenance_stamps("") == ""


class TestClassifyPdfTextLayer:
    def test_a_scan_with_a_signature_stamp_is_not_a_text_layer(self) -> None:
        """🔴 The defect this classifier exists to prevent.

        `extract_pdf_text` returns the stamp, non-empty and useless. Every
        caller that tested it for emptiness shipped it as the document.
        """
        layer = classify_pdf_text_layer(_pdf([(ONR_STAMP, True)] * 3))

        assert len(layer.pages) == 3
        assert layer.is_substantive is False
        assert layer.scanned_page_numbers == (1, 2, 3)
        assert layer.text == "", "stamp text must never reach the caller"
        assert all(p.reason == "provenance stamp only" for p in layer.pages)

        # ...while the raw helper happily hands it over — the contrast is
        # the entire point of the new entry point.
        assert "assinador-web" in extract_pdf_text(_pdf([(ONR_STAMP, True)]))

    def test_a_typeset_page_is_read_for_free(self) -> None:
        corpo = "MATRICULA 118408. " * 60  # ~1080 chars — real content
        layer = classify_pdf_text_layer(_pdf([(corpo, False)]))

        assert layer.is_substantive is True
        assert layer.scanned_page_numbers == ()
        assert "MATRICULA 118408" in layer.text

    def test_text_rich_beats_coverage_so_a_watermark_costs_nothing(self) -> None:
        """A digitally-typeset document sitting on a full-page background
        image is real text. Routing it to vision would be a costly, lossy
        answer to a question we can already answer exactly."""
        corpo = "REGISTRO GERAL LIVRO 2. " * 60
        layer = classify_pdf_text_layer(_pdf([(corpo, True)]))

        assert layer.is_substantive is True
        assert layer.pages[0].reason == "text-rich"

    def test_a_mixed_document_reports_which_pages_need_vision(self) -> None:
        corpo = "AVERBACAO NUMERO UM. " * 60
        layer = classify_pdf_text_layer(
            _pdf([(corpo, False), (ONR_STAMP, True), (corpo, False)])
        )

        assert layer.is_substantive is False, "one scanned page taints the whole"
        assert layer.scanned_page_numbers == (2,)
        # The readable halves survive, in document order, and the stamp
        # between them does not.
        assert layer.text == f"{layer.pages[0].text}\n{layer.pages[2].text}"
        assert "assinador-web" not in layer.text

    def test_a_visualizacao_stamp_is_not_a_text_layer(self) -> None:
        """The 83-char sibling of `ONR_STAMP`. It already failed the char
        floor by accident; now it fails for the right reason, which is what
        makes the two document types behave the same."""
        layer = classify_pdf_text_layer(
            _pdf([(ONR_VISUALIZACAO_STAMP, True)] * 7)
        )

        assert layer.is_substantive is False
        assert layer.scanned_page_numbers == (1, 2, 3, 4, 5, 6, 7)
        assert layer.text == ""
        assert all(p.reason == "provenance stamp only" for p in layer.pages)

    def test_a_stamped_scan_that_covers_half_the_page_is_still_a_scan(self) -> None:
        """\U0001f534 THE HOLE THE COVERAGE RULE LEFT OPEN.

        `MATRICULA CANTAGALO.pdf` page 1 is one scanned image inset at
        446x632pt on a 595x842pt page - 0.56 coverage, under the 0.80 floor
        - carrying the 137-char `ONR_STAMP`. Under the coverage-plus-char-
        floor rules it classified `above char floor`, and the page's entire
        content was silently replaced by its own validation link while the
        document reported success.
        """
        fitz = pytest.importorskip("fitz")

        doc = fitz.open()
        page = doc.new_page()  # 595x842 by default
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 280))
        pix.set_rect(pix.irect, (128, 128, 128))
        # Inset, NOT page-sized: this is what puts coverage under the floor.
        page.insert_image(fitz.Rect(85, 21, 531, 653), pixmap=pix)
        page.insert_textbox(
            fitz.Rect(20, 700, 575, 820), ONR_STAMP, fontsize=6
        )
        pdf = doc.tobytes()
        doc.close()

        layer = classify_pdf_text_layer(pdf)

        assert layer.pages[0].is_substantive is False
        assert layer.pages[0].reason == "provenance stamp only"
        assert layer.text == "", "the stamp must never stand in for the page"

    def test_a_short_typeset_page_still_passes_the_char_floor(self) -> None:
        """The floor is narrowed, not removed. A brief but genuine page -
        under 800 chars, no scan under it - is still read for free rather
        than sent to vision."""
        corpo = "IMOVEL: Terreno na Alameda Alemanha, lote 14 quadra D. " * 4
        assert 100 <= len(corpo) < 800
        layer = classify_pdf_text_layer(_pdf([(corpo, False)]))

        assert layer.is_substantive is True
        assert layer.pages[0].reason == "above char floor"

    def test_a_blank_page_is_not_substantive(self) -> None:
        layer = classify_pdf_text_layer(_pdf([("ok", False)]))
        assert layer.is_substantive is False
        assert layer.pages[0].reason == "below char floor"

    def test_empty_and_garbage_bytes_never_raise(self) -> None:
        assert classify_pdf_text_layer(b"").pages == ()
        assert classify_pdf_text_layer(b"not a pdf\x00\x01").pages == ()

    def test_no_pymupdf_degrades_to_one_synthetic_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without PyMuPDF there is no per-page structural signal. The
        fallback is reported honestly — one page for the whole document —
        so a caller can tell that per-page routing is not on offer."""
        pdf = _pdf([("A" * 900, False), ("B" * 900, False)])
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[override]
            if name == "fitz":
                raise ImportError("simulated slim env")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        layer = classify_pdf_text_layer(pdf)

        assert len(layer.pages) == 1, "cannot claim per-page knowledge it lacks"
        assert layer.tooling_available is True

    def test_no_tooling_at_all_is_reported_not_guessed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[override]
            if name in ("fitz", "pdfminer", "pdfminer.high_level"):
                raise ImportError("simulated")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        layer = classify_pdf_text_layer(b"%PDF-x")

        assert layer.pages == ()
        assert layer.tooling_available is False
