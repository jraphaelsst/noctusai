"""Real ffmpeg/ffprobe decode tests on generated fixtures across the accepted formats."""

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
from noctusai_lib.integrations.transcription.types import AudioProbe
from noctusai_lib.integrations.transcription.validation import (
    TranscriptionLimits,
    check_probe,
    normalize_container,
    sniff_container,
)

_HAVE = shutil.which("ffmpeg") and shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(
    not _HAVE, reason="SKIPPED LOUDLY: ffmpeg/ffprobe not installed; decode path NOT exercised"
)

CASES = [
    ("webm", ["-c:a", "libopus"], "webm"),
    ("mp4", ["-c:a", "aac"], "mp4"),
    ("m4a", ["-c:a", "aac"], "mp4"),
    ("ogg", ["-c:a", "libopus"], "ogg"),
    ("mp3", ["-c:a", "libmp3lame"], "mp3"),
    ("wav", ["-c:a", "pcm_s16le"], "wav"),
    ("flac", ["-c:a", "flac"], "flac"),
    ("aiff", ["-c:a", "pcm_s16be"], "aiff"),
    ("aac", ["-c:a", "aac", "-f", "adts"], "aac"),
    ("wma", ["-c:a", "wmav2", "-f", "asf"], "wma"),
]


def _make(ext: str, codec_args: list[str], tmp_path, seconds: float = 2.0, rate: int = 48000) -> bytes:
    out = tmp_path / f"a.{ext}"
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
           f"sine=frequency=440:duration={seconds}", *codec_args, "-ar", str(rate), "-y", str(out)]
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


@pytest.mark.parametrize("ext,args,canonical", CASES)
def test_real_file_passes_sniff_and_check_probe(ext, args, canonical, tmp_path):
    """End to end on REAL bytes + REAL ffprobe output: the sniff and the probe
    verdict agree on one canonical name and the seed validation accepts it.
    (2026-11-13: fixtures with idealized names hid that wav/mp4/webm were refused.)"""
    data = _make(ext, args, tmp_path)
    info = asyncio.run(probe_bytes(data))
    probe = AudioProbe(info.duracao_s, info.codec, info.container)
    assert sniff_container(data) == canonical
    assert normalize_container(info.container) == canonical
    assert check_probe(probe, TranscriptionLimits(min_duration_s=1.0)) is None


def test_moov_at_end_m4a_beyond_pipe_buffer_decodes(tmp_path):
    """A 30 s m4a written WITHOUT +faststart (moov atom after mdat, the layout of
    phone voice memos) is far larger than ffmpeg's pipe buffer; decoding it from a
    pipe failed. The worker reads a seekable temp file, so it must decode whole."""
    data = _make("m4a", ["-c:a", "aac", "-b:a", "128k"], tmp_path, seconds=30, rate=44100)
    assert data.find(b"moov") > data.find(b"mdat") > 0, "fixture must be moov-at-end"
    assert len(data) > 300_000
    info = asyncio.run(probe_bytes(data))
    assert 29.5 < info.duracao_s < 30.5
    audio = asyncio.run(decode_to_float32(data, max_seconds=None))
    assert 29.5 < len(audio) / 16000 < 30.5


def test_temp_files_are_removed(tmp_path, monkeypatch):
    data = _make("ogg", ["-c:a", "libopus"], tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("TMPDIR", str(work))
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", None)  # re-read TMPDIR (stdlib cache, not our code)
    asyncio.run(probe_bytes(data))
    asyncio.run(decode_to_float32(data, max_seconds=None))
    with pytest.raises(MediaError):
        asyncio.run(decode_to_float32(b"not audio at all" * 50, max_seconds=10))
    assert list(work.iterdir()) == []
