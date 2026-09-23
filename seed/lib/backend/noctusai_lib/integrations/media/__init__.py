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
- `RealMediaResolver` — Whisper + vision + ffmpeg + PyMuPDF (Real). Renamed
  2026-09-20 from `OpenAIMediaResolver`: it now accepts a `provider=` (any
  `documents.transcription.OCR_MODELS` key), so the OpenAI-only name would
  lie about scope. Mirrors the sibling `RealImagingAdapter` naming in
  `integrations/imaging/real_adapter.py`.
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
    PdfPage,
    PdfTextLayer,
    boilerplate_line_spans,
    classify_pdf_text_layer,
    clean_extraction_output,
    extract_pdf_text,
    pdf_text_tooling_available,
    strip_provenance_stamps,
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
    max_pages: int | None = -1,
    provider: str | None = None,
    render_dpi_policy: object | None = None,
) -> MediaResolver:
    """Return a media resolver.

    `FakeMediaResolver` by default (dev/test — deterministic, no IO). Pass
    `real=True` for `RealMediaResolver` (composes the seed LLM entry
    points + ffmpeg + PyMuPDF). The real adapter is imported lazily so the
    Fake path is importable without ffmpeg/PyMuPDF present.

    Args:
        real: Select the real, multi-provider-capable resolver.
        document_prompt: Product-specific document/vision framing override
            (kept type-first to avoid pathological prompt-obedience —
            see `real_adapter` docstring). Real only.
        scene_prompt: Video scene-description prompt override. Real only.
        org_id: Forwarded to the seed LLM entry points for per-org key
            resolution + budget accounting. Real only.
        max_pages: Page cap for rasterize→vision on a PDF. Omit for the
            adapter's default (3); pass `None` for EVERY page, which is what
            a document whose later pages can reverse its meaning needs — a
            certidão's averbação, for instance. The sentinel `-1` means
            "not specified" so `None` can keep its own meaning. Real only.
        provider: Which vendor reads a scanned page / image — any key of
            `documents.providers.OCR_MODELS`. `None` = the seed's canonical
            DOCUMENT provider (`DEFAULT_DOCUMENT_PROVIDER`, Anthropic since
            2026-09-22) for the vision paths; audio still goes to Whisper.
            Real only.
        render_dpi_policy: `None` (the default) leaves every scanned-PDF
            consumer's render DPI unchanged. Forwarded verbatim to
            `RealMediaResolver` → `documents.make_document_transcriber` —
            see `documents.transcription.RenderDpiPolicy` /
            `identity_document_render_dpi_policy`. Typed loosely (`object`)
            so this module never imports `documents.transcription` just to
            type-hint a passthrough. Real only.
    """
    if not real:
        return FakeMediaResolver()

    # Lazy import — keeps the Fake path importable in slim environments
    # where ffmpeg / PyMuPDF are absent (mirrors google_calendar factory).
    from noctusai_lib.integrations.media.real_adapter import RealMediaResolver

    kwargs = {
        "document_prompt": document_prompt,
        "scene_prompt": scene_prompt,
        "org_id": org_id,
        "provider": provider,
        "render_dpi_policy": render_dpi_policy,
    }
    if max_pages != -1:
        kwargs["max_pages"] = max_pages
    return RealMediaResolver(**kwargs)


__all__ = [
    "InboundMedia",
    "ResolvedMedia",
    "MediaKind",
    "MediaResolver",
    "FakeMediaResolver",
    "PdfPage",
    "PdfTextLayer",
    "boilerplate_line_spans",
    "classify_media_kind",
    "classify_pdf_text_layer",
    "clean_extraction_output",
    "extract_pdf_text",
    "get_media_resolver",
    "pdf_text_tooling_available",
    "strip_provenance_stamps",
]
