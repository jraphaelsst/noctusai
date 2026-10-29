"""Real ffmpeg/ffprobe helpers, exercised against tiny lavfi-generated clips."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from noctusai_lib.integrations.media import (
    FfmpegNotInstalled,
    MediaProbeError,
    VideoProbe,
    extract_audio,
    extract_frames,
    ffmpeg_available,
    orientation,
    probe_duration,
    probe_video,
)

pytestmark = pytest.mark.skipif(
    not ffmpeg_available(), reason="ffmpeg/ffprobe not installed on this test host"
)

_MISSING = "noctus-no-such-binary"


def _clip(path: Path, size: str, *, audio: bool = False, rotate: int | None = None) -> Path:
    src = path.with_suffix(".src.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=blue:s={size}:d=2:r=10"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:d=2", "-shortest"]
    subprocess.run(cmd + [str(src)], check=True)
    if rotate is None:
        return src.rename(path)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-display_rotation", str(rotate),
                    "-i", str(src), "-c", "copy", str(path)], check=True)
    return path


def test_probe_landscape(tmp_path):
    p = probe_video(_clip(tmp_path / "a.mp4", "640x360"))
    assert (p.width, p.height, p.rotation) == (640, 360, 0)
    assert p.duration_s == pytest.approx(2.0, abs=0.3)
    assert orientation(p) == "landscape"


def test_probe_portrait_and_square(tmp_path):
    assert orientation(probe_video(_clip(tmp_path / "p.mp4", "360x640"))) == "portrait"
    assert orientation(probe_video(_clip(tmp_path / "s.mp4", "320x320"))) == "square"


def test_rotation_side_data_flips_orientation(tmp_path):
    p = probe_video(_clip(tmp_path / "r.mp4", "640x360", rotate=90))
    assert (p.width, p.height) == (640, 360)  # stored dims unchanged
    assert p.rotation in (90, 270)
    assert (p.display_width, p.display_height) == (360, 640)
    assert orientation(p) == "portrait"


def test_orientation_is_pure():
    assert orientation(VideoProbe(1920, 1080, None, 0)) == "landscape"
    assert orientation(VideoProbe(1920, 1080, None, 90)) == "portrait"
    assert orientation(VideoProbe(1920, 1080, None, 180)) == "landscape"


def test_extract_frames_are_jpeg_and_capped(tmp_path):
    clip = _clip(tmp_path / "f.mp4", "1280x720")
    frames = extract_frames(clip, (0.25, 0.6), max_px=320)
    assert len(frames) == 2
    for f in frames:
        assert f[:3] == b"\xff\xd8\xff"
    # capped to 320 on the longer edge: decode it back via ffprobe
    out = tmp_path / "frame.jpg"
    out.write_bytes(frames[0])
    p = probe_video(out)
    assert max(p.width, p.height) == 320


def test_extract_audio_ogg_opus_from_bytes_and_path(tmp_path):
    clip = _clip(tmp_path / "au.mp4", "320x180", audio=True)
    for src in (clip, clip.read_bytes()):
        audio = extract_audio(src)
        assert audio[:4] == b"OggS"


def test_probe_duration_reads_audio_only_media(tmp_path):
    audio = extract_audio(_clip(tmp_path / "d.mp4", "320x180", audio=True))
    assert probe_duration(audio, suffix=".ogg") == pytest.approx(2.0, abs=0.3)
    with pytest.raises(MediaProbeError):
        probe_duration(b"not media", suffix=".ogg")
    with pytest.raises(FfmpegNotInstalled):
        probe_duration(audio, suffix=".ogg", ffprobe_bin=_MISSING)


def test_extract_audio_without_audio_stream_is_typed(tmp_path):
    clip = _clip(tmp_path / "mute.mp4", "320x180")
    with pytest.raises(MediaProbeError):
        extract_audio(clip)


def test_corrupt_file_is_media_probe_error(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video at all")
    with pytest.raises(MediaProbeError):
        probe_video(bad)
    with pytest.raises(MediaProbeError):
        extract_frames(bad, (0.5,))


def test_missing_binary_fails_loudly_never_none(tmp_path):
    clip = _clip(tmp_path / "x.mp4", "320x180", audio=True)
    with pytest.raises(FfmpegNotInstalled):
        probe_video(clip, ffprobe_bin=_MISSING)
    with pytest.raises(FfmpegNotInstalled):
        extract_frames(clip, (0.5,), ffmpeg_bin=_MISSING)
    with pytest.raises(FfmpegNotInstalled):
        extract_audio(clip, ffmpeg_bin=_MISSING)
    assert ffmpeg_available(ffmpeg_bin=_MISSING) is False
