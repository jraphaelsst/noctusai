"""Deterministic in-memory TTS: writes a valid silent WAV, timings paced at `wpm`.

Same guards as the Real (consent first), so a product test of the refusal path
runs against the Fake unchanged. Cost model: `creditos_por_caractere` per char.
"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Optional

from noctusai_lib.integrations.tts.elevenlabs_adapter import destino, exigir_consentimento
from noctusai_lib.integrations.tts.types import CloneResult, ConsentChecker, PalavraTiming, TtsResult

_RATE = 8000


class FakeTtsClient:
    def __init__(
        self,
        *,
        out_dir: Path,
        org_id: Optional[str] = None,
        consent: Optional[ConsentChecker] = None,
        wpm: float = 165.0,
        creditos_por_caractere: float = 1.0,
    ) -> None:
        self._out_dir = Path(out_dir)
        self._org = org_id
        self._consent = consent
        self._wpm = wpm
        self._cpc = creditos_por_caractere
        self.calls: list[tuple] = []

    def estimate(self, text: str, model: str) -> Optional[float]:
        return round(len(text) * self._cpc, 2)

    def synthesize(self, text: str, voice_id: str, model: str, *, consent_ref: str, output_path: Optional[str] = None,
                   **_opts) -> TtsResult:
        exigir_consentimento(self._consent, self._org, voice_id, consent_ref)
        per_word = 60.0 / self._wpm
        timings, t = [], 0.0
        for w in text.split():
            timings.append(PalavraTiming(w, round(t, 3), round(t + per_word, 3)))
            t += per_word
        dur = round(t, 3)
        target = destino(self._out_dir, text, "wav", output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(target), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(_RATE)
            w.writeframes(b"\x00\x00" * int(_RATE * dur))
        self.calls.append(("synthesize", voice_id, model, len(text)))
        return TtsResult(str(target), timings, len(text), int(round(len(text) * self._cpc)), f"fake-{len(self.calls)}",
                         dur, creditos_fonte="fake", audio_s_fonte="alinhamento")

    def clone_instant(self, name: str, samples, *, consent_ref: str, **_kw) -> CloneResult:
        exigir_consentimento(self._consent, self._org, consent_ref, consent_ref)
        self.calls.append(("clone", name))
        return CloneResult(f"fakevoice{len(self.calls):04d}")
