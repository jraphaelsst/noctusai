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
    modo_medicao: bool = False,
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
        escalar_releitura: Conditional conciliation (owner direction
            2026-10-13): read ONCE with the routed primary model
            (`documents.roteamento`), judge every critical field
            (`documents.confianca`), and only when one is `duvidoso` read
            ONCE more with the routed fallback model and reconcile those
            fields (`releitura.conciliar`: agreement -> stored, disagreement
            -> empty + both readings for review). `True` (the default) — on
            for the identity family. `False` is the per-org OFF SWITCH: the
            single read is returned as before, with no reconciliation.
        modo_medicao: 🔴 EVALUATION HARNESSES ONLY. The always-two-reads
            agreement gate (`releitura.deve_escalar` + `mesclar` + a third
            read for unsettled fields) — the behaviour production had before
            the routing table; kept to MEASURE models, never to serve. A caller resolving a per-org off switch
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
        modo_medicao=modo_medicao,
    )


__all__ = ["make_identity_extractor"]
