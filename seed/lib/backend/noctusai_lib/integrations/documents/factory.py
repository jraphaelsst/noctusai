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
    provider: Optional[str] = None,
    escalar_releitura: bool = True,
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
            default (`None` — EVERY page, up to `documents.transcription.
            MAX_VISION_PAGES`). A certidão de casamento is the canonical case
            for why every page matters: the marriage is on page 1 and the
            AVERBAÇÃO that dissolved it is further in, so a truncated read
            does not lose detail — it returns the opposite answer. Pass a
            concrete N only to deliberately lower the cap below that safety
            ceiling.
        provider: Which vendor reads a scanned page — any key of
            `documents.transcription.OCR_MODELS` (`"openai"` /
            `"anthropic"` / `"gemini"`). `None` = the seed's canonical
            document provider (`providers.DEFAULT_DOCUMENT_PROVIDER`) —
            this is a MANUAL selection, nothing here fails over to another
            vendor. See `noctusai_lib.integrations.llm.resolve_llm_provider`
            for the per-org switch a caller resolves this from.
        escalar_releitura: Re-read a triggering document (`leitura_
            comprometida`, or a core field missing for its declared type —
            see `documents.releitura.deve_escalar`) with a stronger model
            (`documents.providers.ESCALATION_OCR_MODELS`) before returning.
            `True` (the default) — on by default for the identity family,
            per owner decision. A caller resolving a per-org off switch
            passes `False` through here; see
            `social_wiring...api_keys_store.resolve_releitura_habilitada`
            for that consume seam.
    """
    if not real:
        return FakeIdentityExtractor()

    from noctusai_lib.integrations.documents.real import LadderIdentityExtractor

    return LadderIdentityExtractor(
        org_id=org_id,
        document_prompt=document_prompt,
        max_pages=max_pages,
        provider=provider,
        escalar_releitura=escalar_releitura,
    )


__all__ = ["make_identity_extractor"]
