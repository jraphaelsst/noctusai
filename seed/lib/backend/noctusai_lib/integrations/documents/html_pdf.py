"""HTML → PDF bytes via `xhtml2pdf` — the ONE call site the platform's PDF
documents go through.

WHY THIS EXISTS
---------------
Owner requirement (2026-09-14): "Use xhtml2pdf on all PDFs to style and
create a UI for documents." By 2026-09-23 the same `pisa.CreatePDF` dance
(BytesIO dest, error check, resource policy, reportlab's process-global
`invariant` toggle) had been written four times — `render_abnt_pdf`, ERP's
and social-wiring's certidão converters, and igig's orçamento/contrato
documents. Four hand-rolled copies disagree on the parts that matter: one
fetched remote resources, one swallowed errors into ``None``. This module is
the recurrence-rule lift; a new PDF document calls :func:`render_html_pdf`.

TWO DECISIONS, MADE ONCE
------------------------
* **Nothing is fetched.** The HTML is rendered from the given string only —
  ``ResourceAccessPolicy(allow_remote=False, base_dir=None)``. A document
  generated from user-supplied data must never make the server reach out to a
  URL the data names (SSRF), and a document that silently depends on a
  network fetch renders differently depending on the day. Embed images as
  ``data:`` URIs if you need them.
* **Failure raises.** xhtml2pdf reports problems as an error COUNT on the
  status object, not an exception; a caller that forgets to check it stores a
  broken or empty PDF. :func:`render_html_pdf` raises :class:`HtmlPdfError`
  instead. A caller with a real fallback (a certidão keeping the provider's
  original URL) catches it explicitly.

FONTS
-----
xhtml2pdf's core fonts (Helvetica/Times/Courier) are WinAnsi (cp1252): every
pt-BR glyph is covered, emoji and most symbols are not. See
`abnt.UnsupportedGlyphError` for the strict variant; this helper does not
police text — a caller rendering user text should strip or map what cp1252
cannot carry (see :func:`cp1252_safe`).
"""
from __future__ import annotations

import io
import logging

__all__ = ["HtmlPdfError", "render_html_pdf", "cp1252_safe"]

logger = logging.getLogger(__name__)


class HtmlPdfError(RuntimeError):
    """xhtml2pdf could not render the document (its error count was > 0)."""


def cp1252_safe(text: str, *, replacement: str = "") -> str:
    """Drop (or replace) every character the core PDF fonts cannot draw.

    Core fonts would otherwise render an emoji as an empty box or nothing at
    all — silently. Removing it at the boundary is the honest version.
    """
    out: list[str] = []
    for ch in text:
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            if replacement:
                out.append(replacement)
            continue
        out.append(ch)
    return "".join(out)


def render_html_pdf(html: str, *, deterministic: bool = False) -> bytes:
    """Render one self-contained HTML document to PDF bytes.

    ``deterministic=True`` flips reportlab's process-global
    ``rl_config.invariant`` around this build only (fixed ``/CreationDate``
    and file ``/ID``), so identical input yields identical bytes — what a
    golden-file test or a content hash needs. Restored unconditionally.

    Raises :class:`HtmlPdfError` when xhtml2pdf reports an error.
    """
    from reportlab import rl_config
    from xhtml2pdf import pisa
    from xhtml2pdf.config.resources import ResourceAccessPolicy

    buffer = io.BytesIO()
    previous_invariant = rl_config.invariant
    if deterministic:
        rl_config.invariant = 1
    try:
        status = pisa.CreatePDF(
            html,
            dest=buffer,
            encoding="utf-8",
            resource_policy=ResourceAccessPolicy(allow_remote=False, base_dir=None),
        )
    finally:
        rl_config.invariant = previous_invariant
    if status.err:
        logger.error("xhtml2pdf reported %d error(s) rendering a document", status.err)
        raise HtmlPdfError(f"xhtml2pdf reported {status.err} error(s) rendering the document")
    data = buffer.getvalue()
    if not data.startswith(b"%PDF"):
        raise HtmlPdfError("xhtml2pdf produced no PDF output")
    return data
