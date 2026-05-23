"""Audio extraction + chunking with ffmpeg.

Course classes are long; OpenAI's transcription endpoint caps uploads at ~25MB.
We extract a compact mono 16kHz mp3 (good for speech, small) then split it into
time-based chunks so any length transcribes reliably.
"""
from __future__ import annotations

import shutil
import subprocess  # noqa: S404 (ffmpeg is a trusted local binary)
from pathlib import Path

from app.logging_config import get_logger

logger = get_logger(__name__)


class AudioToolError(RuntimeError):
    """ffmpeg missing or a conversion failed."""


def ffmpeg_available() -> bool:
    """True if the `ffmpeg` binary is on PATH."""
    return shutil.which("ffmpeg") is not None


def _require_ffmpeg() -> None:
    if not ffmpeg_available():
        raise AudioToolError(
            "ffmpeg not found on PATH. Install it (macOS: `brew install ffmpeg`)."
        )


def _run(cmd: list[str]) -> None:
    logger.info("ffmpeg: %s", " ".join(cmd[:6]) + (" …" if len(cmd) > 6 else ""))
    result = subprocess.run(  # noqa: S603 (args are constructed, not shell)
        cmd, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise AudioToolError(
            f"ffmpeg failed (exit {result.returncode}):\n{result.stderr[-2000:]}"
        )


def extract_audio(video_path: Path, out_path: Path) -> Path:
    """Extract speech-optimized audio (mono, 16kHz, mp3) from a video.

    Returns the written audio path.
    """
    _require_ffmpeg()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",            # drop video
            "-ac", "1",       # mono
            "-ar", "16000",   # 16kHz
            "-b:a", "48k",    # compact
            str(out_path),
        ]
    )
    return out_path


def split_audio(audio_path: Path, chunk_seconds: int, out_dir: Path) -> list[Path]:
    """Split audio into ~`chunk_seconds` segments. Returns chunk paths in order.

    If the audio is shorter than one chunk, returns a single-element list with the
    original file (no needless re-encode).
    """
    _require_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / f"{audio_path.stem}_%03d{audio_path.suffix}"
    _run(
        [
            "ffmpeg", "-y",
            "-i", str(audio_path),
            "-f", "segment",
            "-segment_time", str(chunk_seconds),
            "-c", "copy",
            str(pattern),
        ]
    )
    chunks = sorted(out_dir.glob(f"{audio_path.stem}_*{audio_path.suffix}"))
    if not chunks:
        # Audio shorter than a segment → ffmpeg may emit a single file; fall back.
        return [audio_path]
    return chunks


__all__ = ["extract_audio", "split_audio", "ffmpeg_available", "AudioToolError"]
