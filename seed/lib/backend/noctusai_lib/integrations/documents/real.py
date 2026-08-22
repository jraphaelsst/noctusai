"""The real extractor — the two-rung ladder, then the pure parser.

WHY THIS COMPOSES `integrations.media` RATHER THAN RE-DOING IT
-------------------------------------------------------------
`media` already owns "bytes → text": PDF text layer via PyMuPDF with a
pdfminer fallback, and rasterize→vision (with refusal-retry) for scanned
documents. Re-implementing that here would fork a validated seam — which
is exactly what `products/erp-imobiliario/.../matricula_service.py` did,
and why it pays for a vision call on every page of PDFs that carry a
perfectly good text layer.

So this module owns only what `media` does not: **choosing the cheapest
rung that works, and turning the resulting text into typed fields.**

THE LADDER
----------
1. **PDF text layer** (`extract_pdf_text`) — free, exact, no LLM call. A
   digitally-generated document stops here.
2. **Rasterize → vision** (`get_media_resolver(real=True)`) — for images
   and for PDFs whose text layer came back empty (a scan or a photo).

Which rung answered is recorded on the result, because it is the best
available predictor of transcription error and the thing an auditor needs
to see later.

🔴 RESIDUAL RISK, STATED PLAINLY
--------------------------------
The plausibility gate in `birthdate` catches gross OCR damage (a year of
1830, a date in 2027). It does NOT catch a confusion between two
*plausible* years — `1980` misread as `1930` passes every check this
module can make. That risk is inherent to reading a photographed
document, and it is why the consumer contract requires storing
`source` + `matched_label` as provenance: the value stays attributable and
correctable rather than becoming an anonymous fact in a column.
"""
from __future__ import annotations

import logging
from typing import Optional

from noctusai_lib.integrations.documents.birthdate import find_birthdate
from noctusai_lib.integrations.documents.fake import classify_kind
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    IdentityFields,
    TextSource,
)

logger = logging.getLogger(__name__)

_PDF_MIMETYPES = frozenset({"application/pdf"})


class LadderIdentityExtractor:
    """Text-layer-first, vision-second identity extractor.

    Construct via `make_identity_extractor(real=True)`.
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
        # Injected in tests; built lazily otherwise so importing this
        # module never drags in PyMuPDF / the LLM stack.
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

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> IdentityFields:
        kind = classify_kind(mimetype, filename)
        if not content:
            return IdentityFields(
                kind=kind,
                error="empty_document",
                error_message="no bytes to read",
            )

        text, source, err = await self._to_text(content, mimetype, filename)
        if err is not None:
            return IdentityFields(kind=kind, source=source, error=err[0], error_message=err[1])
        if not text.strip():
            # Legible pipeline, nothing readable in it. Not an error —
            # a caller must be able to tell this apart from a crash,
            # because retrying it is pointless.
            return IdentityFields(kind=kind, source=source)

        value, confidence, label = find_birthdate(text)
        return IdentityFields(
            kind=kind,
            data_nascimento=value,
            confidence=ExtractionConfidence(confidence),
            source=source,
            matched_label=label,
        )

    async def _to_text(
        self, content: bytes, mimetype: Optional[str], filename: Optional[str]
    ) -> tuple[str, TextSource, Optional[tuple[str, str]]]:
        """Cheapest rung that yields text. Never raises."""
        is_pdf = (mimetype or "").lower() in _PDF_MIMETYPES or (
            filename or ""
        ).lower().endswith(".pdf")

        if is_pdf:
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
            logger.warning("identity extraction: resolver failed: %s", exc)
            return ("", TextSource.NENHUMA, ("resolver_failed", str(exc)))

        if getattr(resolved, "error", None):
            return (
                "",
                TextSource.NENHUMA,
                (resolved.error, getattr(resolved, "error_message", "") or ""),
            )
        return (getattr(resolved, "text", "") or "", TextSource.OCR, None)


__all__ = ["LadderIdentityExtractor"]
