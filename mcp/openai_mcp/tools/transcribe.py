"""openai.transcribe — audio file → text via Whisper."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mcp.types import Tool

from _kit.errors import typed_error

from .. import openai_client
from ..settings import get_settings
from ..types import TranscribeInput, TranscribeOutput

logger = logging.getLogger(__name__)


async def handle_transcribe(args: dict) -> dict:
    try:
        inp = TranscribeInput(**args)
    except Exception as exc:
        return {"error": typed_error(exc, status=422)}
    p = Path(inp.audio_path).expanduser().resolve()
    if not p.exists():
        return {"error": typed_error(
            FileNotFoundError(f"audio_path not found: {inp.audio_path}"),
            status=404,
        )}
    try:
        client = openai_client.get_client()
    except Exception as exc:
        return {"error": typed_error(exc, status=503)}
    model = inp.model or get_settings().default_audio_model
    kwargs: dict[str, Any] = {"model": model, "response_format": "verbose_json"}
    if inp.language:
        kwargs["language"] = inp.language
    try:
        with p.open("rb") as fh:
            resp = client.audio.transcriptions.create(file=fh, **kwargs)
    except Exception as exc:
        return {"error": typed_error(exc, status=502)}
    return TranscribeOutput(
        ok=True,
        model=model,
        text=getattr(resp, "text", ""),
        language=getattr(resp, "language", None),
        duration=getattr(resp, "duration", None),
    ).model_dump()


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="openai.transcribe",
            description=(
                "Transcribe an audio file to text via Whisper. Pass a local "
                "file path (mp3, wav, m4a, webm, etc.). Optional `language` "
                "is an ISO-639-1 code (e.g. 'pt', 'en') — Whisper auto-detects "
                "if omitted. Returns text + detected language + duration."
            ),
            inputSchema=TranscribeInput.model_json_schema(),
        ),
    ]


HANDLERS: dict[str, Any] = {"openai.transcribe": handle_transcribe}


def register(server) -> None:
    pass
