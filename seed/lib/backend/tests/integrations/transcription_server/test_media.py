"""Real ffmpeg/ffprobe decode tests on generated webm/mp4/ogg fixtures."""

from __future__ import annotations

import asyncio
import shutil
import subprocess

import pytest

from noctusai_lib.integrations.transcription.server.media import (
    MediaError,
    decode_to_float32,
    probe_bytes,
)

_HAVE = shutil.which("ffmpeg") and shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(
    not _HAVE, reason="SKIPPED LOUDLY: ffmpeg/ffprobe not installed; decode path NOT exercised"
)

CASES = [
    ("webm", ["-c:a", "libopus"], "webm"),
    ("mp4", ["-c:a", "aac"], "mp4"),
    ("ogg", ["-c:a", "libopus"], "ogg"),
]


def _make(ext: str, codec_args: list[str], tmp_path, seconds: float = 2.0) -> bytes:
    out = tmp_path / f"a.{ext}"
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
           f"sine=frequency=440:duration={seconds}", *codec_args, "-ar", "48000", "-y", str(out)]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        pytest.skip(f"SKIPPED LOUDLY: this ffmpeg build cannot encode {ext}: {r.stderr[-200:]!r}")
    return out.read_bytes()


@pytest.mark.parametrize("ext,args,_", CASES)
def test_decode_16k_mono_float32(ext, args, _, tmp_path):
    data = _make(ext, args, tmp_path)
    audio = asyncio.run(decode_to_float32(data, max_seconds=60))
    assert audio.dtype.name == "float32"
    assert audio.ndim == 1
    assert 1.8 < len(audio) / 16000 < 2.3
    assert abs(audio).max() <= 1.0 and abs(audio).max() > 0.05


@pytest.mark.parametrize("ext,args,_", CASES)
def test_probe_reports_duration(ext, args, _, tmp_path):
    data = _make(ext, args, tmp_path)
    info = asyncio.run(probe_bytes(data))
    assert 1.8 < info.duracao_s < 2.3
    assert info.codec


def test_decode_caps_at_max_seconds(tmp_path):
    data = _make("webm", ["-c:a", "libopus"], tmp_path, seconds=5)
    audio = asyncio.run(decode_to_float32(data, max_seconds=2))
    assert len(audio) / 16000 <= 2.05


def test_garbage_is_media_error():
    with pytest.raises(MediaError):
        asyncio.run(decode_to_float32(b"not audio at all" * 50, max_seconds=10))
    with pytest.raises(MediaError):
        asyncio.run(probe_bytes(b"not audio at all" * 50))
