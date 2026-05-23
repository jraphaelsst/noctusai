"""Audio transcription via OpenAI.

Signature mirrors `noctusai_lib.integrations.llm.transcribe_audio(audio: bytes,
*, model=None, ...)` so the caller ports unchanged on absorption.
"""
from __future__ import annotations

from typing import Optional

from app.config import get_settings
from app.integrations.llm.client import get_client


async def transcribe_audio(
    audio: bytes,
    *,
    model: Optional[str] = None,
    language: Optional[str] = None,
    filename: str = "audio.mp3",
) -> str:
    """Transcribe audio bytes to text.

    Args:
        audio: Raw audio file bytes (mp3/m4a/wav/...).
        model: Override the transcription model (default: settings.transcribe_model).
        language: ISO-639-1 hint (default: settings.transcribe_language).
        filename: Upload filename — its extension tells OpenAI the format.

    Returns the transcribed text.
    """
    settings = get_settings()
    client = get_client()
    resp = await client.audio.transcriptions.create(
        model=model or settings.transcribe_model,
        file=(filename, audio),
        language=language or settings.transcribe_language,
        response_format="text",
    )
    # response_format="text" → the SDK returns a plain string.
    return resp if isinstance(resp, str) else getattr(resp, "text", str(resp))


__all__ = ["transcribe_audio"]
