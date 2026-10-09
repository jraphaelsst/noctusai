"""ffmpeg / ffprobe wrappers (subprocess, no `av`). Untrusted media parses HERE."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Optional

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


async def _run(argv: list[str], stdin: bytes, timeout: float) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, out, err


async def probe_bytes(audio: bytes, *, timeout: float = 5.0) -> ProbeInfo:
    argv = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", "-i", "pipe:0",
    ]
    try:
        rc, out, _ = await _run(argv, audio, timeout)
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
            # Piped ogg/webm often carry no container duration: measure by decoding
            # (bounded by the same probe timeout budget).
            audio = await decode_to_float32(audio, max_seconds=3600.0, timeout=timeout)
            duracao = len(audio) / SAMPLE_RATE
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


async def decode_to_float32(
    audio: bytes, *, max_seconds: float, timeout: float = 120.0
) -> np.ndarray:
    """ffmpeg pipe -> 16 kHz mono s16le -> float32 in [-1, 1)."""
    argv = [
        "ffmpeg", "-nostdin", "-v", "error", "-i", "pipe:0",
        "-t", f"{max_seconds:.3f}", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "s16le", "-",
    ]
    try:
        rc, out, _ = await _run(argv, audio, timeout)
    except asyncio.TimeoutError as exc:
        raise MediaError("ffmpeg timeout") from exc
    if rc != 0 or not out:
        raise MediaError("ffmpeg decode failed")
    pcm = np.frombuffer(out[: len(out) - (len(out) % 2)], dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0
