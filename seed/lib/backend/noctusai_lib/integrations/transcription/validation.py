"""Pure upload validation: magic-byte sniffer + limit constants. No IO.

Acceptance is two-step: a cheap magic-byte sniff (refuses non-media before any
ffprobe runs) and then the worker's ffprobe verdict. Both speak ONE canonical
container vocabulary (`CONTAINERS`), and `normalize_container` maps ffprobe's own
`format_name` (``"mov,mp4,m4a,3gp,3g2,mj2"``, ``"matroska,webm"``, ``"asf"`` …)
onto it.

History (2026-11-13): the old allowlist compared ffprobe output against short
names it never emits (``("wav", "pcm")`` vs ``pcm_s16le``; ``"mp4"`` vs
``"mov,mp4,…"``; ``"webm"`` vs ``"matroska,webm"``), so only mp3 and ogg/opus were
ever accepted in practice. The codec is no longer allowlisted: any audio codec the
worker's ffmpeg decodes is transcribable, and the probe already refuses a file
with no audio stream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from noctusai_lib.integrations.transcription.types import AudioProbe

#: Canonical container name -> storage Content-Type. The ONE list; storage keys,
#: `formato` columns and the OpenAI filename extension all use these names.
CONTAINERS: dict[str, str] = {
    "webm": "audio/webm",
    "mkv": "audio/x-matroska",
    "mp4": "audio/mp4",  # the ISO-BMFF family: mp4 / m4a / mov / 3gp
    "ogg": "audio/ogg",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "aiff": "audio/aiff",
    "aac": "audio/aac",  # raw ADTS
    "wma": "audio/x-ms-wma",
    "amr": "audio/amr",
    "caf": "audio/x-caf",
}

# ffprobe `format_name` tokens -> canonical name. A multi-name format_name
# ("mov,mp4,m4a,3gp,3g2,mj2") resolves through its first known token.
_FFPROBE_ALIASES: dict[str, str] = {
    "mov": "mp4", "mp4": "mp4", "m4a": "mp4", "3gp": "mp4", "3g2": "mp4", "mj2": "mp4",
    "matroska": "webm", "webm": "webm",
    "ogg": "ogg", "mp3": "mp3", "wav": "wav", "w64": "wav", "flac": "flac",
    "aiff": "aiff", "aac": "aac", "asf": "wma", "amr": "amr", "caf": "caf",
}


@dataclass(frozen=True)
class TranscriptionLimits:
    """Caps (overridable per product by constructing another instance)."""

    max_bytes: int = 15 * 1024 * 1024
    max_duration_s: float = 600.0
    min_duration_s: float = 1.0
    allowed_containers: frozenset[str] = field(default_factory=lambda: frozenset(CONTAINERS))


DEFAULT_LIMITS = TranscriptionLimits()


def content_type_for(container: Optional[str]) -> str:
    """Storage Content-Type for a canonical container name."""
    return CONTAINERS.get(container or "", "application/octet-stream")


def normalize_container(format_name: str) -> str:
    """ffprobe `format_name` -> canonical name; unknown names pass through unchanged
    (so `check_probe` refuses them instead of guessing)."""
    for token in (format_name or "").lower().split(","):
        canon = _FFPROBE_ALIASES.get(token.strip())
        if canon:
            return canon
    return (format_name or "").lower()


def _is_mpeg_audio_sync(b0: int, b1: int) -> Optional[str]:
    """Frame sync 0xFFE: layer bits 00 = ADTS AAC, otherwise MPEG audio (mp3/mp2)."""
    if b0 != 0xFF or (b1 & 0xE0) != 0xE0:
        return None
    if (b1 >> 3) & 0b11 == 0b01:  # reserved MPEG version
        return None
    return "aac" if (b1 >> 1) & 0b11 == 0 else "mp3"


def sniff_container(data: bytes) -> Optional[str]:
    """Return the canonical container name from leading magic bytes, or None."""
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "mkv" if b"matroska" in data[:64] else "webm"
    if data[4:8] == b"ftyp":
        return "mp4"
    if data[:4] == b"OggS":
        return "ogg"
    if data[:3] == b"ID3":
        return "mp3"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"fLaC":
        return "flac"
    if data[:4] == b"FORM" and data[8:12] in (b"AIFF", b"AIFC"):
        return "aiff"
    if data[:4] == b"caff":
        return "caf"
    if data[:5] == b"#!AMR":
        return "amr"
    if data[:16] == b"\x30\x26\xb2\x75\x8e\x66\xcf\x11\xa6\xd9\x00\xaa\x00\x62\xce\x6c":
        return "wma"
    if len(data) >= 2:
        return _is_mpeg_audio_sync(data[0], data[1])
    return None


def check_size(size: int, limits: TranscriptionLimits = DEFAULT_LIMITS) -> Optional[str]:
    """Return the error code `arquivo_grande` when over the cap, else None."""
    return "arquivo_grande" if size > limits.max_bytes else None


def check_format(
    data: bytes, limits: TranscriptionLimits = DEFAULT_LIMITS
) -> Optional[str]:
    """Return `formato_invalido` when magic bytes are unknown/not allowed."""
    container = sniff_container(data)
    if container is None or container not in limits.allowed_containers:
        return "formato_invalido"
    return None


def check_probe(
    probe: AudioProbe, limits: TranscriptionLimits = DEFAULT_LIMITS
) -> Optional[str]:
    """Return `formato_invalido` / `audio_vazio` / `duracao_excedida`, else None.

    `probe.container` may be ffprobe's raw `format_name`; it is normalized here.
    Any non-empty audio codec is accepted (the worker decodes it with ffmpeg)."""
    if normalize_container(probe.container) not in limits.allowed_containers or not probe.codec:
        return "formato_invalido"
    if probe.duracao_s < limits.min_duration_s:
        return "audio_vazio"
    if probe.duracao_s > limits.max_duration_s:
        return "duracao_excedida"
    return None
