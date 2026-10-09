"""Deterministic in-memory `Transcriber` for tests and dev."""

from __future__ import annotations

import hashlib
from typing import Optional

from noctusai_lib.integrations.transcription.types import (
    AudioProbe,
    TranscriberBusy,
    TranscriptionRejected,
    TranscriptResult,
)


class FakeTranscriber:
    """Scriptable fake. Text is derived from the audio hash (deterministic).

    - `probes`: map `audio bytes -> AudioProbe` (fixture map); unknown bytes
      get `default_probe`.
    - `script`: list of outcomes consumed one per `transcribe` call; each is
      an Exception instance (raised) or a str (returned as text). Exhausted
      script falls back to the deterministic text.
    """

    def __init__(
        self,
        *,
        probes: Optional[dict[bytes, AudioProbe]] = None,
        default_probe: Optional[AudioProbe] = None,
        script: Optional[list] = None,
    ) -> None:
        self._probes = dict(probes or {})
        self._default_probe = default_probe or AudioProbe(
            duracao_s=5.0, codec="opus", container="webm", sample_rate=48000, canais=1
        )
        self._script = list(script or [])
        self.calls: list[dict] = []

    @staticmethod
    def busy(retry_after_s: float = 15.0) -> TranscriberBusy:
        return TranscriberBusy(retry_after_s)

    @staticmethod
    def rejected(codigo: str = "audio_corrompido") -> TranscriptionRejected:
        return TranscriptionRejected(codigo)

    async def probe(self, audio: bytes) -> AudioProbe:
        return self._probes.get(audio, self._default_probe)

    async def transcribe(
        self, audio: bytes, *, language: str = "pt", max_seconds: float
    ) -> TranscriptResult:
        self.calls.append({"bytes": len(audio), "language": language, "max_seconds": max_seconds})
        if self._script:
            step = self._script.pop(0)
            if isinstance(step, Exception):
                raise step
            text = str(step)
        else:
            text = f"transcricao-fake-{hashlib.sha256(audio).hexdigest()[:8]}"
        probe = await self.probe(audio)
        return TranscriptResult(
            text=text,
            duracao_s=probe.duracao_s,
            idioma=language,
            modelo="fake",
            rtf=0.0,
        )
