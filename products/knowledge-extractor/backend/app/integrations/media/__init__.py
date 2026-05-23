"""Media seam — audio extraction + chunking via ffmpeg.

Maps onto noc's multimodal `noctusai_lib.integrations.media` on absorption.
"""
from app.integrations.media.audio import (
    AudioToolError,
    extract_audio,
    ffmpeg_available,
    split_audio,
)

__all__ = ["extract_audio", "split_audio", "ffmpeg_available", "AudioToolError"]
