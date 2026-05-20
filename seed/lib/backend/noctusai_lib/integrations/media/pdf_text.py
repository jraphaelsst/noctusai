"""PDF text-layer extraction — `extract_pdf_text(bytes) -> str`.

Lifted 2026-05-19 by `social-wiring-google-seed-consume` Phase 6a-drive
from the social-wiring `media_service._extract_pdf_text` + reconciled
with `OpenAIMediaResolver._pdf_text_layer` (the existing private
implementation inside this seed module — same logic, now single-sourced
and public). Becomes the canonical PDF→text helper for both the
multimodal `OpenAIMediaResolver` document path AND non-resolver
consumers (e.g. `DriveFileContent.text` for `application/pdf`).

Implementation order (matches the absorbed product + ERP `certidoes_service`
convention):

1. **PyMuPDF (`fitz`) `page.get_text()` per page**, joined with newlines
   between non-empty pages. Faster than pdfminer for the text-layer case
   and we already depend on it for the rasterize fallback inside
   `OpenAIMediaResolver`.
2. **`pdfminer.high_level.extract_text(...)` fallback** when PyMuPDF
   is unavailable (slim envs) — defensive: both ship in social-wiring's
   `requirements.txt`. Used to be the primary in the absorbed product;
   demoted per the W1.E5 reconcile (commit `61d684f`).
3. **Returns `""` on any failure** (no PyMuPDF *and* no pdfminer; corrupted
   PDF; empty text layer of a scanned doc). Callers can fall through to
   rasterize-then-vision (`OpenAIMediaResolver._pdf_rasterize` +
   `analyze_image_with_refusal_retry`).

Tooling-availability signal: `pdf_text_tooling_available()` returns
False when both libs are absent so a consumer can distinguish
"extraction returned empty because the doc has no text" from
"extraction returned empty because we have no extractor."
"""

from __future__ import annotations

import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF using PyMuPDF, falling back to pdfminer.

    Returns the joined page text (one newline between non-empty pages)
    or `""` on any failure. Never raises into the caller — failures
    are logged at `debug` and the caller falls through to other
    extraction paths (rasterize + vision)."""
    text, _ok = _extract_pdf_text_with_signal(pdf_bytes)
    return text


def pdf_text_tooling_available() -> bool:
    """True iff at least one of PyMuPDF or pdfminer.six can be imported.

    Use this to distinguish "extractor unavailable" from "extractor
    returned empty for this doc" in degraded-mode error messages."""
    try:
        import fitz  # type: ignore  # noqa: F401  # PyMuPDF
        return True
    except ImportError:
        pass
    try:
        import pdfminer.high_level  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


def _extract_pdf_text_with_signal(pdf_bytes: bytes) -> tuple[str, bool]:
    """Return `(text, tooling_available)`.

    The `tooling_available` bool is True when at least one extractor
    library was importable (text may still be empty for scanned docs);
    False only when neither PyMuPDF nor pdfminer is installed."""
    if not pdf_bytes:
        return ("", pdf_text_tooling_available())

    # Try PyMuPDF first — faster + matches noc's certidoes_service
    # convention. ModuleNotFoundError falls through to pdfminer;
    # any other exception logs at debug and falls through too (so a
    # corrupt PDF doesn't crash the caller; pdfminer may handle it).
    try:
        import fitz  # type: ignore  # PyMuPDF

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception:
            logger.debug("PyMuPDF: failed to open document", exc_info=True)
        else:
            try:
                chunks = [doc[i].get_text().strip() for i in range(len(doc))]
            except Exception:
                logger.debug("PyMuPDF: get_text failed", exc_info=True)
                chunks = []
            finally:
                doc.close()
            joined = "\n".join(c for c in chunks if c)
            if joined:
                return (joined, True)
            # PyMuPDF available but yielded no text — try pdfminer
            # (different parser may handle some text-layer encodings
            # PyMuPDF struggles with).
    except ImportError:
        pass

    try:
        from pdfminer.high_level import extract_text  # type: ignore
    except ImportError:
        # Neither lib available — caller may fall through to rasterize.
        return ("", False)

    try:
        return (extract_text(BytesIO(pdf_bytes)) or "", True)
    except Exception:
        logger.debug("pdfminer extract_text failed", exc_info=True)
        return ("", True)


__all__ = ["extract_pdf_text", "pdf_text_tooling_available"]
