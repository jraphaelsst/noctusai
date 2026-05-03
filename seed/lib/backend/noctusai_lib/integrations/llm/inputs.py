"""LLM input-shape helpers — vision (image) + audio file payloads.

Pure functions that adapt raw bytes into the shapes required by LLM SDKs:
- `image_bytes_to_data_url`: OpenAI vision-input data URL
- `audio_bytes_to_named_buffer`: OpenAI audio-transcription file buffer
"""

from __future__ import annotations

import base64
from io import BytesIO


def image_bytes_to_data_url(image_bytes: bytes, mimetype: str) -> str:
    """Build a `data:` URL for OpenAI vision-input image payloads."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mimetype};base64,{b64}"


def audio_bytes_to_named_buffer(audio_bytes: bytes, filename: str) -> BytesIO:
    """Wrap audio bytes in a `BytesIO` with a `name` attribute, satisfying
    OpenAI's audio-transcription file-upload contract."""
    buffer = BytesIO(audio_bytes)
    buffer.name = filename  # type: ignore[attr-defined]
    return buffer


__all__ = ["image_bytes_to_data_url", "audio_bytes_to_named_buffer"]
