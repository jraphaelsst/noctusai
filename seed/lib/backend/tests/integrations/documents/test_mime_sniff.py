"""`mime_sniff.sniff_real_mimetype` — content wins over the declared
mimetype/filename. Live P2 test (2026-09-30): a `*.jpg` upload (declared
`image/jpeg`) was actually a PDF, and the vision call rejected the PDF
bytes outright rather than the ladder trying the free text-layer rung.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.mime_sniff import sniff_real_mimetype


class TestKnownSignatures:
    def test_pdf_magic_bytes(self):
        assert sniff_real_mimetype(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n") == "application/pdf"

    def test_jpeg_magic_bytes(self):
        assert sniff_real_mimetype(b"\xff\xd8\xff\xe0\x00\x10JFIF") == "image/jpeg"

    def test_png_magic_bytes(self):
        assert sniff_real_mimetype(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR") == "image/png"

    def test_webp_magic_bytes(self):
        content = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBPVP8 "
        assert sniff_real_mimetype(content) == "image/webp"

    def test_heic_magic_bytes(self):
        content = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"
        assert sniff_real_mimetype(content) == "image/heic"

    def test_heic_sibling_brand_mif1(self):
        content = b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00"
        assert sniff_real_mimetype(content) == "image/heic"


class TestNoOpinion:
    def test_empty_bytes(self):
        assert sniff_real_mimetype(b"") is None

    def test_unrecognised_bytes(self):
        assert sniff_real_mimetype(b"this is plain text, not a document") is None

    def test_a_riff_container_that_is_not_webp(self):
        """RIFF is also AVI/WAV's own container header — only the `WEBP`
        form-type at bytes 8-12 is claimed."""
        content = b"RIFF" + b"\x00\x00\x00\x00" + b"AVI LIST"
        assert sniff_real_mimetype(content) is None

    def test_a_short_buffer_never_raises(self):
        assert sniff_real_mimetype(b"\xff\xd8") is None
        assert sniff_real_mimetype(b"RIFF") is None


class TestResolveUploadMimetype:
    """Extension-less office files (WhatsApp/Drive downloads) arrive as
    application/octet-stream; the bytes decide."""

    def test_generic_declared_resolved_from_bytes(self):
        from noctusai_lib.integrations.documents.mime_sniff import resolve_upload_mimetype

        assert resolve_upload_mimetype("application/octet-stream", b"\xff\xd8\xff\xe0\x00") == "image/jpeg"
        assert resolve_upload_mimetype("", b"%PDF-1.7") == "application/pdf"
        assert resolve_upload_mimetype(None, b"\x89PNG\r\n\x1a\n....") == "image/png"
        assert resolve_upload_mimetype("application/octet-stream", b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"

    def test_contradicting_declaration_loses_to_bytes(self):
        from noctusai_lib.integrations.documents.mime_sniff import resolve_upload_mimetype

        assert resolve_upload_mimetype("image/jpeg", b"%PDF-1.4") == "application/pdf"

    def test_declared_pdf_with_executable_bytes_is_not_a_document(self):
        from noctusai_lib.integrations.documents.mime_sniff import resolve_upload_mimetype

        assert resolve_upload_mimetype("application/pdf", b"MZ\x90\x00") == "application/octet-stream"

    def test_unknown_bytes_keep_declared(self):
        from noctusai_lib.integrations.documents.mime_sniff import resolve_upload_mimetype

        assert resolve_upload_mimetype("text/plain", b"hello") == "text/plain"
        assert resolve_upload_mimetype("application/octet-stream", b"hello") == "application/octet-stream"

    def test_ensure_extension(self):
        from noctusai_lib.integrations.documents.mime_sniff import ensure_extension

        assert ensure_extension("Bruno - CNH", "application/pdf") == "Bruno - CNH.pdf"
        assert ensure_extension("Espelho IPTU 2026", "image/jpeg") == "Espelho IPTU 2026.jpg"
        assert ensure_extension("a.jpeg", "image/jpeg") == "a.jpeg"
