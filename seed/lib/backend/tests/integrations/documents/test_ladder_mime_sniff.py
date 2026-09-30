"""`DocumentTextLadder.to_text` — the content-vs-declared mimetype sniff
wired in ahead of routing. Live P2 test (2026-09-30): a `*.jpg` upload
(declared `image/jpeg`) was actually a PDF; `looks_like_pdf` trusted the
declared type, skipped the free text-layer rung, and forwarded the PDF
bytes downstream tagged as an image — the vision call rejected them outright
(`resolve_failed`, "Could not process image"). `mime_sniff.sniff_real_
mimetype` fixes this at the one shared choke point every extractor's text
comes through.
"""
from __future__ import annotations

import logging

import pytest

from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
from noctusai_lib.integrations.documents.types import TextSource


class _CapturingResolver:
    """Records every `InboundMedia` it is asked to resolve — same
    convention `test_identity_new_fields.py`'s `_FakeResolverCapturingMedia`
    uses, duplicated locally so this file's fixtures never share state with
    that one's."""

    def __init__(self, resposta_texto: str = "vision text") -> None:
        self._resposta_texto = resposta_texto
        self.medias: list = []

    async def resolve(self, media):
        self.medias.append(media)

        class _Resolved:
            error = None
            error_message = None
            text = self._resposta_texto

        return _Resolved()


class TestAMislabelledPdfIsReadAsAPdf:
    """The exact live shape: a PDF's bytes, declared `image/jpeg`, filename
    ending in `.jpg`."""

    @pytest.mark.asyncio
    async def test_a_real_pdf_text_layer_is_tried_despite_the_jpg_label(self):
        fitz = pytest.importorskip("fitz")
        doc = fitz.open()
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(20, 20, 500, 500), "CONTEUDO REAL DO PDF " * 10, fontsize=10)
        pdf_bytes = doc.tobytes()
        doc.close()

        ladder = DocumentTextLadder()
        text, source, err = await ladder.to_text(
            pdf_bytes, mimetype="image/jpeg", filename="867-comp1-certidao-48.jpg"
        )
        assert err is None
        assert source is TextSource.TEXT_LAYER
        assert "CONTEUDO REAL DO PDF" in text

    @pytest.mark.asyncio
    async def test_a_mismatch_is_logged_as_a_warning(self, caplog):
        fitz = pytest.importorskip("fitz")
        doc = fitz.open()
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(20, 20, 500, 500), "TEXTO " * 20, fontsize=10)
        pdf_bytes = doc.tobytes()
        doc.close()

        ladder = DocumentTextLadder()
        with caplog.at_level(logging.WARNING):
            await ladder.to_text(pdf_bytes, mimetype="image/jpeg", filename="foo.jpg")
        assert any(
            "disagrees with the content's own signature" in r.message for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_a_scanned_mislabelled_pdf_reaches_the_resolver_as_a_pdf_not_an_image(self):
        """A PDF whose text layer is empty (a scan) must fall to rung 2
        tagged `application/pdf`, never the declared `image/jpeg` — the
        resolver routes on `InboundMedia.mimetype` alone."""
        resolver = _CapturingResolver()
        ladder = DocumentTextLadder(resolver=resolver)
        text, source, err = await ladder.to_text(
            b"%PDF-1.4\nno real text layer here", mimetype="image/jpeg", filename="scan.jpg"
        )
        assert err is None
        assert source is TextSource.OCR
        assert len(resolver.medias) == 1
        assert resolver.medias[0].mimetype == "application/pdf"


class TestAMislabelledImageIsReadAsAnImage:
    """The reverse mismatch: declared `application/pdf` (and a `.pdf`
    filename), but the bytes are actually a JPEG."""

    @pytest.mark.asyncio
    async def test_routes_to_the_resolver_as_the_sniffed_image_type(self):
        resolver = _CapturingResolver()
        ladder = DocumentTextLadder(resolver=resolver)
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32
        text, source, err = await ladder.to_text(
            jpeg_bytes, mimetype="application/pdf", filename="comprovante.pdf"
        )
        assert err is None
        assert source is TextSource.OCR
        assert len(resolver.medias) == 1
        assert resolver.medias[0].mimetype == "image/jpeg"


class TestNoMismatchIsUnaffected:
    """The overwhelming majority of calls: declared type already agrees
    with the content, or the content doesn't match any known signature —
    byte-for-byte the prior routing, unchanged."""

    @pytest.mark.asyncio
    async def test_a_correctly_declared_pdf_is_unaffected(self):
        fitz = pytest.importorskip("fitz")
        doc = fitz.open()
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(20, 20, 500, 500), "TEXTO NORMAL " * 10, fontsize=10)
        pdf_bytes = doc.tobytes()
        doc.close()

        ladder = DocumentTextLadder()
        text, source, err = await ladder.to_text(
            pdf_bytes, mimetype="application/pdf", filename="doc.pdf"
        )
        assert err is None
        assert source is TextSource.TEXT_LAYER

    @pytest.mark.asyncio
    async def test_content_matching_no_known_signature_keeps_the_declared_type(self):
        resolver = _CapturingResolver()
        ladder = DocumentTextLadder(resolver=resolver)
        text, source, err = await ladder.to_text(
            b"not a recognised file signature at all",
            mimetype="image/png",
            filename="odd.png",
        )
        assert err is None
        assert resolver.medias[0].mimetype == "image/png"
