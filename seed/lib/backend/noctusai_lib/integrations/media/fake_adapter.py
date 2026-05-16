"""Deterministic in-memory media resolver (no IO, no OpenAI, no ffmpeg).

Dev/local fallback when no LLM config is wired, and the test stand-in for
any consumer that doesn't want to hit OpenAI / shell out to ffmpeg /
import PyMuPDF. Same shape as `whatsapp.FakeWahaClient` /
`google_calendar.FakeCalendarAdapter` per
`KB § PATTERNS/seed-fake-real-adapter.md`.

The Fake exercises the SAME classification + output-contract code as the
Real (`classify_media_kind` + `ResolvedMedia`); only the enrichment
(transcription/vision/extraction) is canned. A consumer that passes the
Fake-path tests has validated everything except the external-IO calls.
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.integrations.media.types import (
    InboundMedia,
    MediaKind,
    ResolvedMedia,
    classify_media_kind,
)

# Deterministic canned enrichment per kind. Tests assert on these exactly.
_CANNED_TEXT: dict[MediaKind, str] = {
    MediaKind.AUDIO: "[transcrição de áudio] olá, esta é uma mensagem de voz de teste.",
    MediaKind.IMAGE: "[descrição da imagem] uma fotografia de teste mostrando um cenário simples.",
    MediaKind.VIDEO: (
        "[análise de vídeo] cena: ambiente de teste com 4 keyframes amostrados. "
        "[transcrição de áudio do vídeo] fala de teste contida no vídeo."
    ),
    MediaKind.PDF: (
        "[documento PDF] CONTEÚDO DE TESTE\n"
        "Documento de exemplo com texto extraível. Campo: valor."
    ),
}


class FakeMediaResolver:
    """In-memory `MediaResolver`. Records every resolved blob; serves a
    deterministic enriched-text rendering per classified kind.

    Test pattern::

        resolver = FakeMediaResolver()
        out = await resolver.resolve(
            InboundMedia(content=b"...", mimetype="audio/ogg")
        )
        assert out.kind is MediaKind.AUDIO
        assert "transcrição de áudio" in out.text
        assert resolver.resolved[0].mimetype == "audio/ogg"

    Override the canned text for a specific kind via `set_text(kind, text)`
    to drive consumer branches deterministically; force the degraded path
    via `fail_next(error, message)`.
    """

    def __init__(self) -> None:
        self.resolved: list[InboundMedia] = []
        self._overrides: dict[MediaKind, str] = {}
        self._pending_failure: Optional[tuple[str, str]] = None

    def set_text(self, kind: MediaKind, text: str) -> None:
        """Override the canned enriched text for `kind` (test driving)."""
        self._overrides[kind] = text

    def fail_next(self, error: str, message: str) -> None:
        """Force the next `resolve()` call onto the degraded fallback shape
        (truthful sentence + error code) — exercises consumer error paths."""
        self._pending_failure = (error, message)

    async def resolve(self, media: InboundMedia) -> ResolvedMedia:
        self.resolved.append(media)
        kind = classify_media_kind(media.mimetype, media.filename)

        if self._pending_failure is not None:
            error, message = self._pending_failure
            self._pending_failure = None
            return ResolvedMedia(
                kind=kind,
                text=(
                    "Não foi possível processar o anexo enviado "
                    f"({kind.value}). Detalhe: {message}"
                ),
                error=error,
                error_message=message,
            )

        if kind is MediaKind.UNKNOWN:
            return ResolvedMedia(
                kind=kind,
                text=(
                    "Recebi um anexo cujo tipo não reconheço "
                    f"(mimetype={media.mimetype!r}). Descreva-o em texto, "
                    "por favor."
                ),
                error="unsupported_media_type",
                error_message=f"unclassifiable mimetype={media.mimetype!r}",
            )

        text = self._overrides.get(kind, _CANNED_TEXT[kind])
        return ResolvedMedia(kind=kind, text=text)


__all__ = ["FakeMediaResolver"]
