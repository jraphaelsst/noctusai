"""Tests for the public `extract_pdf_text(...)` helper (lifted
2026-05-19 from social-wiring `media_service._extract_pdf_text`,
single-sourced with `OpenAIMediaResolver._pdf_text_layer`)."""

from __future__ import annotations

import builtins

import pytest

from noctusai_lib.integrations.media import (
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
