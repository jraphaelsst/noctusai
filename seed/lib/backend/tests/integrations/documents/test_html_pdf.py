"""`render_html_pdf` — the shared xhtml2pdf call site.

Assertions read the rendered PDF back with PyMuPDF (already a hard seed
dependency) rather than trusting the HTML handed in.
"""
from __future__ import annotations

import fitz
import pytest

from noctusai_lib.integrations.documents import (
    HtmlPdfError,
    cp1252_safe,
    render_html_pdf,
)


def _texto(pdf: bytes) -> str:
    doc = fitz.open(stream=pdf, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)


def test_renders_real_pdf_with_the_text():
    pdf = render_html_pdf("<html><body><h1>Orçamento</h1><p>Seg, Qua × 2 — R$ 1.500,00</p></body></html>")
    assert pdf.startswith(b"%PDF")
    texto = _texto(pdf)
    assert "Orçamento" in texto
    assert "Seg, Qua × 2" in texto


def test_deterministic_output_is_byte_identical():
    html = "<html><body><p>Mesmo conteúdo</p></body></html>"
    assert render_html_pdf(html, deterministic=True) == render_html_pdf(html, deterministic=True)


def test_deterministic_flag_is_restored():
    from reportlab import rl_config

    antes = rl_config.invariant
    render_html_pdf("<p>x</p>", deterministic=True)
    assert rl_config.invariant == antes


def test_remote_resources_are_never_fetched():
    """An <img> pointing at a URL must not make the server fetch it (SSRF).

    The policy refuses the fetch; the document still renders without it.
    """
    pdf = render_html_pdf(
        '<html><body><img src="http://169.254.169.254/latest/meta-data/x.png"/><p>ok</p></body></html>'
    )
    assert "ok" in _texto(pdf)


def test_failure_raises_instead_of_returning_garbage(monkeypatch):
    from xhtml2pdf import pisa

    class _Status:
        err = 3

    def _falha(*_a, **_k):
        return _Status()

    # External library double — pisa is a vendor dependency, not our code.
    monkeypatch.setattr(pisa, "CreatePDF", _falha)
    with pytest.raises(HtmlPdfError):
        render_html_pdf("<p>x</p>")


def test_cp1252_safe_drops_what_core_fonts_cannot_draw():
    assert cp1252_safe("Olá 🚀 mundo — ç") == "Olá  mundo — ç"
    assert cp1252_safe("a🚀b", replacement="?") == "a?b"
