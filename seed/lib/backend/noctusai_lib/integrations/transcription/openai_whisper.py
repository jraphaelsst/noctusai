"""OpenAI Whisper backend — wraps the unchanged `llm.audio.transcribe_audio`."""

from __future__ import annotations

from typing import Optional

from noctusai_lib.integrations.transcription.types import (
    AudioProbe,
    ProbeNotSupported,
    TranscriptResult,
)
from noctusai_lib.integrations.transcription.validation import sniff_container


class OpenAIWhisperTranscriber:
    """Duration/codec are unknown to the API, so `probe` is unsupported and the
    result carries `duracao_s=None` (quota by probed duration needs the local
    backend)."""

    def __init__(self, *, org_id: Optional[str] = None, model: Optional[str] = None) -> None:
        self._org_id = org_id
        self._model = model

    async def probe(self, audio: bytes) -> AudioProbe:
        raise ProbeNotSupported("openai backend cannot probe audio duration")

    async def transcribe(
        self, audio: bytes, *, language: str = "pt", max_seconds: float
    ) -> TranscriptResult:
        # Imported here, not at module top: the LLM stack pulls every provider SDK
        # (anthropic, openai, …). The self-hosted transcriber image imports this
        # package (server/ lives under it) with only its own deps, so the package
        # must import without the LLM stack (build-transcriber import smoke).
        from noctusai_lib.integrations.llm.audio import transcribe_audio

        container = sniff_container(audio) or "webm"
        text = await transcribe_audio(
            audio,
            model=self._model,
            org_id=self._org_id,
            filename=f"audio.{container}",
            language=language,
        )
        return TranscriptResult(
            text=text,
            duracao_s=None,
            idioma=language,
            modelo=self._model or "openai-whisper",
        )
