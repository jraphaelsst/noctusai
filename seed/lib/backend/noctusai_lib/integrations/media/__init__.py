"""Multimodal inbound-media resolver — Fake + Real + factory.

Turns an inbound media blob (already-downloaded bytes + mimetype/filename)
into **enriched text the chatbot reads as a normal user message**.
Surface-agnostic: same resolver serves WAHA inbound and platform-chat
uploads. Downloading bytes / rewriting vendor-internal URLs is the
caller's (whatsapp integration's) concern — this module starts from bytes.

Lifted + reconciled 2026-05-16 by `projects/social-wiring-absorption/`
Wave 1.E5 from the originating seed-workspace's `media_service.py` (the
`multimodal-stack` promotion manifest). Reconciliation: audio/vision route
through the existing seed `noctusai_lib.integrations.llm` entry points
(NOT direct OpenAI); NEW capabilities added — PDF text via PyMuPDF
(`page.get_text()`, matching noc's `erp-imobiliario` convention) with a
rasterize-then-vision fallback for scanned docs, video keyframe analysis
via ffmpeg, and refusal-retry on every vision call.

**What ships** (`KB § PATTERNS/seed-fake-real-adapter.md` shape):
- `InboundMedia` / `ResolvedMedia` / `MediaKind` value objects.
- `MediaResolver` Protocol + `classify_media_kind` pure classifier.
- `FakeMediaResolver` — deterministic, no IO (dev/test default).
- `OpenAIMediaResolver` — Whisper + vision + ffmpeg + PyMuPDF (Real).
- `get_media_resolver()` factory — Fake by default; Real when `real=True`.

**Output contract the chatbot consumes:** `ResolvedMedia.text` is ALWAYS a
non-empty, human-readable, model-ready string (the chatbot injects it as
the user's message body). On any failure the resolver returns a truthful
fallback sentence and sets `error` (machine code) + `error_message` — it
NEVER raises into the chatbot loop and NEVER returns empty text. `kind`
always reflects the classified category. Persisting `error`/`error_message`
in the durable audit log is `noctusai_lib.domain.chatbot.message_store`'s
job (CHATBOT's package) — this module only produces the shape.

Heavy deps (PyMuPDF / pdfminer) + the `ffmpeg` binary are lazily
imported/shelled, so the Fake path stays importable in slim environments.
"""
from noctusai_lib.integrations.media.fake_adapter import FakeMediaResolver
from noctusai_lib.integrations.media.pdf_text import (
    extract_pdf_text,
    pdf_text_tooling_available,
)
from noctusai_lib.integrations.media.types import (
    InboundMedia,
    MediaKind,
    MediaResolver,
    ResolvedMedia,
    classify_media_kind,
)


def get_media_resolver(
    *,
    real: bool = False,
    document_prompt: str | None = None,
    scene_prompt: str | None = None,
    org_id: str | None = None,
) -> MediaResolver:
    """Return a media resolver.

    `FakeMediaResolver` by default (dev/test — deterministic, no IO). Pass
    `real=True` for `OpenAIMediaResolver` (composes the seed LLM entry
    points + ffmpeg + PyMuPDF). The real adapter is imported lazily so the
    Fake path is importable without ffmpeg/PyMuPDF present.

    Args:
        real: Select the OpenAI-backed resolver.
        document_prompt: Product-specific document/vision framing override
            (kept type-first to avoid pathological prompt-obedience —
            see `real_adapter` docstring). Real only.
        scene_prompt: Video scene-description prompt override. Real only.
        org_id: Forwarded to the seed LLM entry points for per-org key
            resolution + budget accounting. Real only.
    """
    if not real:
        return FakeMediaResolver()

    # Lazy import — keeps the Fake path importable in slim environments
    # where ffmpeg / PyMuPDF are absent (mirrors google_calendar factory).
    from noctusai_lib.integrations.media.real_adapter import OpenAIMediaResolver

    return OpenAIMediaResolver(
        document_prompt=document_prompt,
        scene_prompt=scene_prompt,
        org_id=org_id,
    )


__all__ = [
    "InboundMedia",
    "ResolvedMedia",
    "MediaKind",
    "MediaResolver",
    "FakeMediaResolver",
    "classify_media_kind",
    "extract_pdf_text",
    "get_media_resolver",
    "pdf_text_tooling_available",
]
