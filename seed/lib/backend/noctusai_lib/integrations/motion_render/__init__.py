"""motion_render seam -- Protocol + Fake + Real (preset `papel-explainer` v2) + factory.

    from noctusai_lib.integrations.motion_render import make_motion_renderer
    r = make_motion_renderer()
    spec = r.retime(spec, tts_result.timings)          # refuses unless words match the script 1:1
    out = r.render("papel-explainer", spec, tts_result.audio_path, out_dir)

Subject-neutral: the script, names and illustrations come from the caller's spec; the
illustration library (`shapes.py`) is generic and extensible via `shapes.EXTRAS`.
"""
# NOC-REMEDIATE[media-adapters-phase2]: avatar (HeyGen), layout_render and captions adapters are later slices of the criacao pipeline; this package covers the reel_narrado pilot only (tts + motion_render) — 2026-11-19
from __future__ import annotations

from noctusai_lib.integrations.motion_render.factory import make_motion_renderer
from noctusai_lib.integrations.motion_render.fake_adapter import FakeMotionRenderer
from noctusai_lib.integrations.motion_render.real_adapter import RealMotionRenderer, ferramentas_disponiveis
from noctusai_lib.integrations.motion_render.retime import retime
from noctusai_lib.integrations.motion_render.types import (
    FerramentaAusente,
    LoudnessForaDoAlvo,
    MotionRenderer,
    MotionRenderError,
    RenderResult,
    RetimeRecusado,
    SpecInvalida,
)

__all__ = [
    "FakeMotionRenderer", "FerramentaAusente", "LoudnessForaDoAlvo", "MotionRenderError", "MotionRenderer",
    "RealMotionRenderer", "RenderResult", "RetimeRecusado", "SpecInvalida", "ferramentas_disponiveis",
    "make_motion_renderer", "retime",
]
