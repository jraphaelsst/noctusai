"""`make_motion_renderer` -- Real when ffmpeg + ImageMagick are present, else a declared refusal.

The Fake is an explicit opt-in (`allow_fake=True`); missing tools never silently degrade to it.
"""
from __future__ import annotations

from typing import Callable

from noctusai_lib.integrations.fake_or_refuse import resolve_fake_or_refuse
from noctusai_lib.integrations.motion_render.fake_adapter import FakeMotionRenderer
from noctusai_lib.integrations.motion_render.real_adapter import RealMotionRenderer, ferramentas_disponiveis
from noctusai_lib.integrations.motion_render.types import FerramentaAusente
from noctusai_lib.integrations.motion_render.types import MotionRenderer


def _refuse() -> MotionRenderer:
    raise FerramentaAusente("ffmpeg/ffprobe/magick ausentes -- use a imagem base noctus-seed-backend-media-base")


def make_motion_renderer(*, allow_fake: bool = False,
                         tools_available: Callable[[], bool] = ferramentas_disponiveis) -> MotionRenderer:
    return resolve_fake_or_refuse(
        configured=tools_available(),
        build_real=RealMotionRenderer,
        build_fake=FakeMotionRenderer,
        allow_fake=allow_fake,
        unconfigured=_refuse,
    )
