"""Transcribe an audio file of any length.

Splits into chunks (OpenAI's ~25MB upload cap) and stitches the pieces back into
one transcript. Used as the pipeline's default transcriber.
"""
from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.integrations.llm import transcribe_audio
from app.integrations.media import split_audio
from app.logging_config import get_logger

logger = get_logger(__name__)


async def transcribe_file(audio_path: Path, *, chunk_dir: Path) -> str:
    """Transcribe a (possibly long) audio file into a single transcript string."""
    settings = get_settings()
    chunks = split_audio(audio_path, settings.chunk_seconds, chunk_dir)
    logger.info("transcribing %d chunk(s) of %s", len(chunks), audio_path.name)

    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        logger.info("  chunk %d/%d: %s", i, len(chunks), chunk.name)
        text = await transcribe_audio(
            chunk.read_bytes(), filename=chunk.name
        )
        parts.append(text.strip())
    return "\n\n".join(p for p in parts if p)


__all__ = ["transcribe_file"]
