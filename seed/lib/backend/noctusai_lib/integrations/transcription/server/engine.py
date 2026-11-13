"""Engine seam — the model sits behind `TranscriptionEngine` so tests inject a fake."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


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

    def transcribe(
        self, audio: Any, *, language: str, palavras: bool = False
    ) -> EngineResult:
        """`audio` = float32 mono 16 kHz numpy array. Runs to completion — no deadline."""
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

    def transcribe(
        self, audio: Any, *, language: str, palavras: bool = False
    ) -> EngineResult:
        if self._model is None:
            raise RuntimeError("model not loaded")
        # word_timestamps is passed ONLY when asked: default-off calls are byte-identical.
        extra: dict[str, Any] = {"word_timestamps": True} if palavras else {}
        segments, _info = self._model.transcribe(
            audio, language=language, vad_filter=True, beam_size=5, **extra
        )
        parts: list[str] = []
        segs: list[dict[str, Any]] = []
        # `segments` is a lazy generator: decoding happens as we iterate.
        for seg in segments:
            parts.append(seg.text.strip())
            item: dict[str, Any] = {"inicio": seg.start, "fim": seg.end, "texto": seg.text.strip()}
            if palavras:
                item["palavras"] = [
                    {
                        "texto": w.word.strip(),
                        "inicio": w.start,
                        "fim": w.end,
                        "confianca": w.probability,
                    }
                    for w in (seg.words or [])
                ]
            segs.append(item)
        return EngineResult(text=" ".join(p for p in parts if p).strip(), segmentos=segs)
