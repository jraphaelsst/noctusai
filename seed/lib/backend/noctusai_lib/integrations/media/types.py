"""Media inbound-resolver value objects + Protocol.

The resolver turns an inbound media blob (already-downloaded bytes +
mimetype/filename) into **enriched text the chatbot can reason about as a
normal user message**. Surface-agnostic — the same resolver serves WAHA
inbound and platform-chat uploads. Downloading the bytes / rewriting
vendor-internal URLs is the *caller's* concern (whatsapp integration); this
module starts from bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol, runtime_checkable


class MediaKind(str, Enum):
    """Classified inbound media category (derived from mimetype)."""

    AUDIO = "audio"
    IMAGE = "image"
    VIDEO = "video"
    PDF = "pdf"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class InboundMedia:
    """An inbound media blob to resolve.

    Attributes:
        content: Raw file bytes (already downloaded by the caller).
        mimetype: MIME type as reported by the source (e.g. ``audio/ogg``,
            ``image/jpeg``, ``video/mp4``, ``application/pdf``). May be None
            — `filename` is then used for classification.
        filename: Original filename when known. Primes the document/vision
            prompt ("the model knows what to expect") and is the
            classification fallback when `mimetype` is absent.
        force_vision: PDF only. Skip the text-layer short-circuit even when
            `classify_pdf_text_layer` judges it substantive — the caller
            already read that text and found none of the fields it needs
            (`documents.ladder.DocumentTextLadder.to_text`'s own
            `pular_camada_texto`, which this carries through). Without this,
            `RealMediaResolver._resolve_pdf` independently re-runs the SAME
            classifier, finds the SAME "substantive" verdict, and hands back
            the SAME useless text — the caller's forced retry becomes a
            silent no-op. Measured 2026-09-23: a "CNH Digital" PDF whose
            selectable text is a card-cover boilerplate (real, substantive
            text by the classifier's field-agnostic char-count heuristic)
            while every identity field lives in a small embedded image —
            `sem_dados` on every retry, because vision was never actually
            called. Ignored by every non-PDF branch and by
            `FakeMediaResolver`.
    """

    content: bytes
    mimetype: Optional[str] = None
    filename: Optional[str] = None
    force_vision: bool = False


@dataclass(frozen=True)
class ResolvedMedia:
    """The resolver output the chatbot consumes.

    `text` is the canonical field — the enriched, model-readable rendering
    the chatbot injects as the user's message body. The remaining fields are
    for the durable audit log (see `noctusai_lib.domain.chatbot.message_store`
    — CHATBOT's package; this module only produces the shape).

    Contract guarantees:
    - `text` is ALWAYS a non-empty human-readable string. On any failure the
      resolver returns a truthful fallback sentence (never raises into the
      chatbot loop, never an empty string) and sets `error`.
    - `kind` reflects the classified category even on failure.
    - `error` is None on success; a short machine code (e.g.
      ``download_failed``, ``transcription_empty``, ``pdf_no_text``) on a
      degraded path. `error_message` carries the human detail.
    """

    kind: MediaKind
    text: str
    error: Optional[str] = None
    error_message: Optional[str] = None


@runtime_checkable
class MediaResolver(Protocol):
    """Resolve inbound media to enriched chatbot-readable text.

    Implementations: `FakeMediaResolver` (deterministic, no IO — dev/test
    default) and `RealMediaResolver` (Whisper + vision + ffmpeg keyframes
    + PyMuPDF, multi-provider). Selected via `get_media_resolver()`.
    """

    async def resolve(self, media: InboundMedia) -> ResolvedMedia: ...


def classify_media_kind(
    mimetype: Optional[str], filename: Optional[str] = None
) -> MediaKind:
    """Map a mimetype (or filename extension fallback) to a `MediaKind`.

    Pure function — the single classification authority shared by every
    resolver. Mimetype wins; filename extension is the fallback when the
    mimetype is absent or generic (``application/octet-stream``).
    """
    mt = (mimetype or "").lower().strip()
    if mt and mt != "application/octet-stream":
        if mt.startswith("audio/"):
            return MediaKind.AUDIO
        if mt.startswith("image/"):
            return MediaKind.IMAGE
        if mt.startswith("video/"):
            return MediaKind.VIDEO
        if mt == "application/pdf" or mt.endswith("/pdf"):
            return MediaKind.PDF

    name = (filename or "").lower().strip()
    if name:
        if name.endswith((".mp3", ".m4a", ".wav", ".ogg", ".oga", ".opus", ".webm", ".aac")):
            return MediaKind.AUDIO
        if name.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".heic")):
            return MediaKind.IMAGE
        if name.endswith((".mp4", ".mov", ".mkv", ".avi", ".3gp", ".m4v")):
            return MediaKind.VIDEO
        if name.endswith(".pdf"):
            return MediaKind.PDF

    return MediaKind.UNKNOWN


__all__ = [
    "MediaKind",
    "InboundMedia",
    "ResolvedMedia",
    "MediaResolver",
    "classify_media_kind",
]
