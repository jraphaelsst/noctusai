"""Engine seam — the model sits behind `TranscriptionEngine` so tests inject a fake."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


class EngineTimeout(Exception):
    """The hard deadline passed mid-transcription (checked per decoded segment)."""


@dataclass
class EngineResult:
    text: str
    segmentos: Optional[list[dict[str, Any]]] = field(default=None)


@runtime_checkable
class TranscriptionEngine(Protocol):
    model_name: str

    def load(self) -> None: ...

    @property
    def loaded(self) -> bool: ...

    def transcribe(self, audio: Any, *, language: str, deadline: float) -> EngineResult:
        """`audio` = float32 mono 16 kHz numpy array. `deadline` = `time.monotonic()` value.

        MUST raise `EngineTimeout` once the deadline passes.
        """
        ...


class FasterWhisperEngine:
    """faster-whisper large-v3-turbo, CPU int8, one thread, one worker."""

    def __init__(self, model_path: str, model_name: str = "large-v3-turbo") -> None:
        self._path = model_path
        self.model_name = model_name
        self._model: Any = None

    def load(self) -> None:
        from faster_whisper import WhisperModel  # lazy: heavy, optional extra

        self._model = WhisperModel(
            self._path,
            device="cpu",
            compute_type="int8",
            cpu_threads=1,
            num_workers=1,
        )

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def transcribe(self, audio: Any, *, language: str, deadline: float) -> EngineResult:
        if self._model is None:
            raise RuntimeError("model not loaded")
        segments, _info = self._model.transcribe(
            audio, language=language, vad_filter=True, beam_size=5
        )
        parts: list[str] = []
        segs: list[dict[str, Any]] = []
        # `segments` is a lazy generator: decoding happens as we iterate, so the
        # deadline is enforced at segment (~30 s window) granularity.
        for seg in segments:
            if time.monotonic() > deadline:
                raise EngineTimeout()
            parts.append(seg.text.strip())
            segs.append({"inicio": seg.start, "fim": seg.end, "texto": seg.text.strip()})
        if time.monotonic() > deadline:
            raise EngineTimeout()
        return EngineResult(text=" ".join(p for p in parts if p).strip(), segmentos=segs)
