"""Transcription value objects, typed errors, and the `Transcriber` Protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


class TranscriptionError(Exception):
    """Base for every transcription-seam error."""


class TranscriberBusy(TranscriptionError):
    """The engine is occupied (retryable). Carries the server's hint.

    A job worker should RESCHEDULE (not consume a retry) after
    `retry_after_s` — see `noctusai_lib.domain.jobs.repo.RescheduleLater`.
    """

    def __init__(self, retry_after_s: float = 15.0, message: str = "transcriber busy"):
        super().__init__(message)
        self.retry_after_s = float(retry_after_s)


class TranscriptionRejected(TranscriptionError):
    """Permanent: the audio cannot be transcribed (decode/type/limit failure).
    Retrying the same bytes will fail the same way."""

    def __init__(self, codigo: str, message: str = ""):
        super().__init__(message or codigo)
        self.codigo = codigo


class TranscriberUnavailable(TranscriptionError):
    """The engine is unreachable / timed out / returned an unexpected failure
    (retryable with backoff)."""


class ProbeNotSupported(TranscriptionError):
    """The backend cannot probe duration/codec (OpenAI has no probe endpoint)."""


@dataclass(frozen=True)
class AudioProbe:
    duracao_s: float
    codec: str
    container: str
    sample_rate: Optional[int] = None
    canais: Optional[int] = None


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    duracao_s: Optional[float]
    idioma: str
    modelo: str
    rtf: Optional[float] = None
    segmentos: Optional[list[dict]] = field(default=None)


@runtime_checkable
class Transcriber(Protocol):
    """Surface every transcription backend implements."""

    async def probe(self, audio: bytes) -> AudioProbe:
        """Inspect container/codec/duration without transcribing."""
        ...

    async def transcribe(
        self, audio: bytes, *, language: str = "pt", max_seconds: float
    ) -> TranscriptResult:
        """Transcribe `audio`. Raises `TranscriberBusy`,
        `TranscriptionRejected` or `TranscriberUnavailable`."""
        ...
