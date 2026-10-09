"""Pure upload validation: magic-byte sniffer + limit constants. No IO."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from noctusai_lib.integrations.transcription.types import AudioProbe


@dataclass(frozen=True)
class TranscriptionLimits:
    """Caps (overridable per product by constructing another instance)."""

    max_bytes: int = 15 * 1024 * 1024
    max_duration_s: float = 600.0
    min_duration_s: float = 1.0
    allowed_containers: frozenset[str] = frozenset({"webm", "ogg", "mp4", "mp3", "wav"})
    # (container, codec) pairs accepted after probing.
    allowed_codecs: frozenset[tuple[str, str]] = frozenset(
        {
            ("webm", "opus"),
            ("ogg", "opus"),
            ("mp4", "aac"),
            ("mp3", "mp3"),
            ("wav", "pcm"),
        }
    )


DEFAULT_LIMITS = TranscriptionLimits()


def sniff_container(data: bytes) -> Optional[str]:
    """Return the container name from leading magic bytes, or None."""
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if data[4:8] == b"ftyp":
        return "mp4"
    if data[:4] == b"OggS":
        return "ogg"
    if data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return "mp3"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
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
    """Return `formato_invalido` / `audio_vazio` / `duracao_excedida`, else None."""
    if (
        probe.container not in limits.allowed_containers
        or (probe.container, probe.codec) not in limits.allowed_codecs
    ):
        return "formato_invalido"
    if probe.duracao_s < limits.min_duration_s:
        return "audio_vazio"
    if probe.duracao_s > limits.max_duration_s:
        return "duracao_excedida"
    return None
