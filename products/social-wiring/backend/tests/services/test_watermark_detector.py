"""Watermark module: verdict decision, defensive parsing, and the Real
detector's ffmpeg frame extraction + request shape (vision injected)."""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess

import pytest

from app.modules.youtube.services.watermark import (
    LOGO_ASSET,
    LogoVerdict,
    VisionWatermarkDetector,
    WatermarkDetectionError,
    parse_verdicts,
    pick_logo_version,
)

T = LogoVerdict(True, 0.95)
F = LogoVerdict(False, 0.9)


def test_pick_exactly_one_logo():
    assert pick_logo_version([F, T]) == 1
    assert pick_logo_version([T, F]) == 0


@pytest.mark.parametrize("verdicts", [
    [F, F], [T, T], [T, LogoVerdict(None, 0.0)], [LogoVerdict(True, 0.3), F],
    [T, LogoVerdict(False, 0.2)], [],
])
def test_pick_never_guesses(verdicts):
    assert pick_logo_version(verdicts) is None


def test_parse_verdicts_tolerates_fences_and_missing_ids():
    text = 'ok:\n```json\n{"videos":[{"id":"a","has_logo":true,"confidence":0.9}]}\n```'
    v = parse_verdicts(text, 2)
    assert v[0] == LogoVerdict(True, 0.9)
    assert v[1].has_logo is None


@pytest.mark.parametrize("bad", ["", "no json", '{"videos": 3}', '{"x":1}'])
def test_parse_verdicts_bad_reply(bad):
    try:
        out = parse_verdicts(bad, 2)
    except WatermarkDetectionError:
        return
    assert all(x.has_logo is None for x in out)


def test_logo_asset_is_shipped():
    assert LOGO_ASSET.exists() and LOGO_ASSET.stat().st_size > 1000


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg not installed")
def test_real_detector_extracts_frames_and_sends_one_request(tmp_path):
    clips = []
    for name in ("a.mp4", "b.mp4"):
        p = tmp_path / name
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
             "color=c=blue:s=640x360:d=2:r=10", str(p)], check=True)
        clips.append(p)
    seen = {}

    async def vision(images, prompt, **kw):
        seen.update(n=len(images), prompt=prompt, kw=kw)
        return json.dumps({"videos": [
            {"id": "A", "has_logo": False, "confidence": 0.9},
            {"id": "B", "has_logo": True, "confidence": 0.9}]})

    det = VisionWatermarkDetector(model="claude-sonnet-5", vision_fn=vision)
    verdicts = asyncio.run(det.detect(clips))
    assert pick_logo_version(verdicts) == 1
    assert seen["n"] == 1 + 2 * 2  # logo + 2 frames per video, ONE request
    assert seen["kw"] == {"provider": "anthropic", "model": "claude-sonnet-5"}
    assert "Vídeo A" in seen["prompt"] and "Vídeo B" in seen["prompt"]


def test_real_detector_vision_error_is_typed(tmp_path):
    p = tmp_path / "a.mp4"
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=red:s=320x180:d=1:r=10", str(p)], check=True)

    async def vision(*a, **k):
        raise RuntimeError("quota exceeded")

    det = VisionWatermarkDetector(vision_fn=vision)
    with pytest.raises(WatermarkDetectionError):
        asyncio.run(det.detect([p, p]))
