"""The text ladder: bytes → the cheapest rung that yields readable text.

WHY THIS IS ITS OWN MODULE
--------------------------
This logic began as `LadderIdentityExtractor._to_text` — private, and
correctly so while exactly one extractor existed. A second one arrived
(`matricula_extractor.LadderMatriculaExtractor`, which reads a property's
registry number off a certidão), and it needs the *identical* first half:
try the PDF's own text layer, fall back to rasterize→vision, and record
which rung answered.

That is N=2 on a decision with real money attached. Copying it would have
produced the exact failure `integrations.documents` was created to stop —
`erp-imobiliario/app/services/matricula_service.py` is a product-local PDF
reader that pays for a vision call on every page of PDFs that carry a
perfectly good text layer, because it never learned rung 1 existed.

So the rung-choosing half lives here, once, and the extractors above it own
only the part that actually differs: which parsers to run on the text and
what typed shape to return.

WHAT THIS DELIBERATELY DOES *NOT* DO
------------------------------------
It does not classify the document, temper confidence, or interpret anything.
It answers one question — "what text is in these bytes, and how sure can you
be of the transcription?" — and the `TextSource` it returns is the whole of
its opinion. Confidence policy belongs to the extractor above, because it is
field-specific: a vision-read *name* is a suggestion (it can be plausibly
wrong), while a vision-read *gênero* is either right or absent.
"""
from __future__ import annotations

import logging
from typing import Optional

from noctusai_lib.integrations.documents.types import TextSource

logger = logging.getLogger(__name__)

_PDF_MIMETYPES = frozenset({"application/pdf"})


def looks_like_pdf(mimetype: Optional[str], filename: Optional[str]) -> bool:
    """Is this worth trying the text-layer rung on?

    Checks the declared mimetype AND the filename extension, because
    browsers routinely upload PDFs as `application/octet-stream` and a
    missed PDF costs a vision call that was never needed.
    """
    return (mimetype or "").lower() in _PDF_MIMETYPES or (
        filename or ""
    ).lower().endswith(".pdf")


class DocumentTextLadder:
    """Cheapest-rung text extraction, shared by every document extractor.

    1. **PDF text layer** (`extract_pdf_text`) — free, exact, no LLM call.
       A digitally-generated document stops here.
    2. **Rasterize → vision** — for images, and for PDFs whose text layer
       came back empty (a scan, or a photo of one).
    """

    def __init__(
        self,
        *,
        org_id: Optional[str] = None,
        document_prompt: Optional[str] = None,
        resolver=None,
    ) -> None:
        self._org_id = org_id
        self._document_prompt = document_prompt
        # Injected in tests; built lazily otherwise so importing this module
        # never drags in PyMuPDF / the LLM stack.
        self._resolver = resolver

    def _get_resolver(self):
        if self._resolver is None:
            from noctusai_lib.integrations.media import get_media_resolver

            self._resolver = get_media_resolver(
                real=True,
                org_id=self._org_id,
                document_prompt=self._document_prompt,
            )
        return self._resolver

    async def to_text(
        self,
        content: bytes,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> tuple[str, TextSource, Optional[tuple[str, str]]]:
        """Return `(text, source, error)`. NEVER raises.

        These extractors run detached from the request that triggered them,
        so an exception here would surface nowhere and would leave the
        document stuck mid-pipeline forever. Every failure is returned as a
        value instead.
        """
        if looks_like_pdf(mimetype, filename):
            try:
                from noctusai_lib.integrations.media import extract_pdf_text

                text = extract_pdf_text(content)
            except ImportError:
                # Slim environment: fall through to the resolver, which
                # reports its own tooling gap truthfully.
                text = ""
            except Exception:
                logger.debug("pdf text-layer extraction failed", exc_info=True)
                text = ""
            if text.strip():
                return (text, TextSource.TEXT_LAYER, None)

        # Rung 2 — images always land here; PDFs land here when the text
        # layer was empty (scanned/photographed).
        try:
            from noctusai_lib.integrations.media import InboundMedia

            resolved = await self._get_resolver().resolve(
                InboundMedia(content=content, mimetype=mimetype, filename=filename)
            )
        except Exception as exc:  # noqa: BLE001 - background job must not die
            logger.warning("document text ladder: resolver failed: %s", exc)
            return ("", TextSource.NENHUMA, ("resolver_failed", str(exc)))

        if getattr(resolved, "error", None):
            return (
                "",
                TextSource.NENHUMA,
                (resolved.error, getattr(resolved, "error_message", "") or ""),
            )
        return (getattr(resolved, "text", "") or "", TextSource.OCR, None)


__all__ = ["DocumentTextLadder", "looks_like_pdf"]
