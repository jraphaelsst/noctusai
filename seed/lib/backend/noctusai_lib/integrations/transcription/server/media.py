"""ffmpeg / ffprobe wrappers (subprocess, no `av`). Untrusted media parses HERE.

The upload is written to a private temp file and ffmpeg/ffprobe read it by PATH,
never through `pipe:0`: a pipe is not seekable, and ISO-BMFF files whose `moov`
atom sits at the end (phone voice memos, Safari recordings, ffmpeg's default mp4
output) cannot be demuxed from a pipe once they outgrow its buffer (2026-11-13:
every m4a above ~190 KB failed with "ffmpeg decode failed"). Seekable input also
gives ffprobe a real container duration, so the decode-to-measure fallback is
only for formats that genuinely carry none.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np

SAMPLE_RATE = 16000


class MediaError(Exception):
    """Undecodable / unprobeable input -> HTTP 422 `audio_corrompido`."""


@dataclass
class ProbeInfo:
    duracao_s: float
    codec: str
    container: str
    sample_rate: Optional[int]
    canais: Optional[int]


@contextmanager
def _as_file(audio: bytes) -> Iterator[str]:
    """The upload as a private (0600) temp file, removed on exit."""
    fd, path = tempfile.mkstemp(prefix="noctus-audio-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(audio)
        yield path
    finally:
        os.unlink(path)


async def _run(argv: list[str], timeout: float) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, out, err


async def probe_bytes(audio: bytes, *, timeout: float = 5.0) -> ProbeInfo:
    with _as_file(audio) as path:
        argv = [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", "-i", path,
        ]
        try:
            rc, out, _ = await _run(argv, timeout)
        except asyncio.TimeoutError as exc:
            raise MediaError("ffprobe timeout") from exc
        if rc != 0:
            raise MediaError("ffprobe failed")
        try:
            data = json.loads(out)
            stream = next(s for s in data.get("streams", []) if s.get("codec_type") == "audio")
            fmt = data.get("format", {})
            raw = fmt.get("duration") or stream.get("duration")
            if raw in (None, "N/A"):
                # Some containers carry no duration at all: measure by decoding
                # (bounded by the same probe timeout budget).
                pcm = await _decode_path(path, max_seconds=3600.0, timeout=timeout)
                duracao = len(pcm) / SAMPLE_RATE
            else:
                duracao = float(raw)
            return ProbeInfo(
                duracao_s=duracao,
                codec=str(stream.get("codec_name", "")),
                container=str(fmt.get("format_name", "")),
                sample_rate=int(stream["sample_rate"]) if stream.get("sample_rate") else None,
                canais=int(stream["channels"]) if stream.get("channels") else None,
            )
        except (StopIteration, TypeError, ValueError, KeyError) as exc:
            raise MediaError("no audio stream") from exc


async def _decode_path(path: str, *, max_seconds: Optional[float], timeout: float) -> np.ndarray:
    limit = ["-t", f"{max_seconds:.3f}"] if max_seconds is not None else []
    argv = [
        "ffmpeg", "-nostdin", "-v", "error", "-i", path,
        *limit, "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "s16le", "-",
    ]
    try:
        rc, out, _ = await _run(argv, timeout)
    except asyncio.TimeoutError as exc:
        raise MediaError("ffmpeg timeout") from exc
    if rc != 0 or not out:
        raise MediaError("ffmpeg decode failed")
    pcm = np.frombuffer(out[: len(out) - (len(out) % 2)], dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0


async def decode_to_float32(
    audio: bytes, *, max_seconds: Optional[float], timeout: float = 120.0
) -> np.ndarray:
    """ffmpeg (seekable temp file) -> 16 kHz mono s16le -> float32 in [-1, 1).
    `max_seconds=None` decodes it all."""
    with _as_file(audio) as path:
        return await _decode_path(path, max_seconds=max_seconds, timeout=timeout)
