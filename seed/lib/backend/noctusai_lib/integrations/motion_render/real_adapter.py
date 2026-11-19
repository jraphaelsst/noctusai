"""Real renderer: ImageMagick + ffmpeg subprocesses (the seed MEDIA base image ships both)."""
from __future__ import annotations

import shutil
from typing import Optional

from noctusai_lib.integrations.media.video import ffmpeg_available
from noctusai_lib.integrations.motion_render import preset as P
from noctusai_lib.integrations.motion_render.papel_engine import PapelEngine
from noctusai_lib.integrations.motion_render.retime import retime as _retime
from noctusai_lib.integrations.motion_render.types import FerramentaAusente, RenderResult, SpecInvalida


def ferramentas_disponiveis() -> bool:
    return ffmpeg_available() and shutil.which("magick") is not None


class RealMotionRenderer:
    """`render` is synchronous and CPU-heavy (admit it through the hardware gate / a worker, never the event loop)."""

    def render(self, preset: str, spec: dict, audio_path: Optional[str], out_dir: str) -> RenderResult:
        if preset not in P.PRESETS_SUPORTADOS:
            raise SpecInvalida(f"preset desconhecido: {preset!r} (suportados: {sorted(P.PRESETS_SUPORTADOS)})",
                               codigo="preset_desconhecido")
        if not ferramentas_disponiveis():
            raise FerramentaAusente("ffmpeg/ffprobe/magick ausentes -- use a imagem base noctus-seed-backend-media-base")
        return PapelEngine(out_dir).render(spec, audio_path)

    def retime(self, spec: dict, timings: list) -> dict:
        return _retime(spec, timings)
