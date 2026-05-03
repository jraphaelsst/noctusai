"""Transcribe audio bytes to text via the active LLM provider.

Routes through ``noctusai_lib.integrations.llm.audio.transcribe_audio``,
which today defaults to OpenAI Whisper. Other providers raise
``ProviderNotImplemented`` unless a dev guard is set.
"""

from __future__ import annotations

import base64

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field


class TranscribeInput(BaseModel):
    audio_base64: str = Field(
        description=(
            "Audio bytes encoded as base64. Any container the provider supports "
            "(ogg, mp3, wav, m4a, webm, etc.)."
        )
    )
    filename: str = Field(
        default="audio.ogg",
        description="Filename hint (extension matters for codec detection).",
    )
    language: str | None = Field(
        default="pt",
        description="ISO-639-1 language code, or null to auto-detect.",
    )
    model: str | None = Field(
        default=None,
        description="Override the provider's default audio model for this call.",
    )
    provider: str | None = Field(
        default=None,
        description="Override the active LLM provider (default: configured provider).",
    )
    org_id: str | None = Field(
        default=None,
        description="Scope API-key resolution to a specific org.",
    )


class TranscribeOutput(BaseModel):
    text: str


async def transcribe(payload: TranscribeInput) -> TranscribeOutput:
    """Transcribe audio bytes (base64) to plain text via the active LLM provider."""
    from noctusai_lib.integrations.llm.audio import transcribe_audio

    audio_bytes = base64.b64decode(payload.audio_base64)
    text = await transcribe_audio(
        audio_bytes,
        model=payload.model,
        provider=payload.provider,
        org_id=payload.org_id,
        filename=payload.filename,
        language=payload.language,
    )
    return TranscribeOutput(text=text)


def register(server: FastMCP) -> None:
    server.tool(
        name="llm.audio.transcribe",
        description=transcribe.__doc__,
    )(transcribe)
