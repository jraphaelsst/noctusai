"""Identity-extractor factory — Fake by default, Real on request.

Fake-by-default is the same posture every seed IO module takes: a
consumer that forgets to configure the real adapter gets deterministic
behaviour, not a surprise LLM bill or an import error in a slim image.
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.integrations.documents.fake import FakeIdentityExtractor
from noctusai_lib.integrations.documents.types import IdentityExtractor


def make_identity_extractor(
    *,
    real: bool = False,
    org_id: Optional[str] = None,
    document_prompt: Optional[str] = None,
    max_pages: int | None = -1,
) -> IdentityExtractor:
    """Return an identity extractor.

    Args:
        real: Select `LadderIdentityExtractor` (PDF text layer → vision).
            Imported lazily so the Fake path stays importable without
            PyMuPDF or the LLM stack.
        org_id: Forwarded to the LLM entry points for per-org key
            resolution and budget accounting.
        document_prompt: Product-specific framing for the vision rung.
        max_pages: Page cap for the vision rung. Omit for the adapter's
            default (3 pages — right for an ID card); pass `None` to read
            EVERY page, which a document whose later pages can reverse its
            meaning requires. A certidão de casamento is the canonical case:
            the marriage is on page 1 and the AVERBAÇÃO that dissolved it is
            further in, so a truncated read does not lose detail — it returns
            the opposite answer.
    """
    if not real:
        return FakeIdentityExtractor()

    from noctusai_lib.integrations.documents.real import LadderIdentityExtractor

    return LadderIdentityExtractor(
        org_id=org_id, document_prompt=document_prompt, max_pages=max_pages
    )


__all__ = ["make_identity_extractor"]
