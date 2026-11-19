"""Fake renderer: a tiny valid mp4 via ffmpeg testsrc, or a flagged stub file when ffmpeg is absent."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from noctusai_lib.integrations.media.video import ffmpeg_available
from noctusai_lib.integrations.motion_render.retime import retime as _retime
from noctusai_lib.integrations.motion_render.types import RenderResult


class FakeMotionRenderer:
    def __init__(self, *, ffmpeg_ok: Optional[bool] = None) -> None:
        self._ffmpeg_ok = ffmpeg_ok  # None = detect; False forces the flagged stub (tests, ffmpeg-less hosts)
        self.calls: list[tuple[str, Optional[str]]] = []

    def render(self, preset: str, spec: dict, audio_path: Optional[str], out_dir: str) -> RenderResult:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        self.calls.append((preset, audio_path))
        palavras = spec.get("palavras") or []
        dur = round((max((w["fim_s"] for w in palavras), default=1.0)) + spec.get("cauda_s", 0.5), 3)
        mp4 = out / "final.mp4"
        stub = not (ffmpeg_available() if self._ffmpeg_ok is None else self._ffmpeg_ok)
        if stub:
            mp4.write_bytes(b"NOC-FAKE-MP4-STUB")  # not a playable video; `stub=True` says so
        else:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                            f"testsrc=size=90x160:rate=10:duration={min(dur, 3):.2f}", "-pix_fmt", "yuv420p", str(mp4)],
                           check=True, capture_output=True)
        srt = out / "legenda.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nfake\n", encoding="utf-8")
        narrado = audio_path is not None
        return RenderResult(str(mp4), str(srt), [], {
            "lufs": -14.0 if narrado else None, "true_peak_db": -1.5 if narrado else None,
            "violacoes_zona_segura": [], "velocidade_render_x": 1.0, "duracao_s": dur, "fake": True,
        }, stub=stub)

    def retime(self, spec: dict, timings: list) -> dict:
        return _retime(spec, timings)
