"""ffmpeg/ffprobe video helpers — probe, orientation, stills, audio track.

The ONE seed home for shelling out to ffmpeg/ffprobe, so a product wires
video features instead of hand-rolling subprocess calls (social-wiring had
three copies: watermark stills, the upload orientation probe, and
`media_service`'s keyframes/audio/duration).

**Fails loudly, by contract.** The pre-seed helpers returned ``None`` when
the binary was missing, which silently classified every video's orientation
"unknown" in an image that never installed ffmpeg. Here:

- `FfmpegNotInstalled` — the binary is not on PATH. A deploy/config error:
  callers must NOT swallow it into a fallback value. Products get the
  binaries by building ``FROM noctus-seed-backend-media-base``
  (``seed/docker/Dockerfile.backend-base`` target ``media``).
- `MediaProbeError` — the binary ran but could not decode the input
  (corrupt/non-video file, no audio stream, timeout). Callers that treat
  "can't read this file" as a normal outcome may catch THIS ONLY.

**No Fake adapter (deliberate).** Per `KB § PATTERNS/backend/
seed-fake-real-adapter.md` a Fake exists to stand in for a *networked or
credentialed* vendor. These are pure functions over a local binary with no
credentials and millisecond runtimes: the Real path is the test path
(tests generate tiny clips with ffmpeg's ``lavfi`` source). The binary
names are parameters (``ffprobe_bin`` / ``ffmpeg_bin``) so a missing
binary is testable without patching anything.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

Orientation = Literal["landscape", "portrait", "square"]

_PROBE_TIMEOUT_S = 30
_FRAME_TIMEOUT_S = 60
_AUDIO_TIMEOUT_S = 600


class FfmpegNotInstalled(RuntimeError):
    """The ffmpeg/ffprobe binary is not on PATH (deploy/config error)."""


class MediaProbeError(RuntimeError):
    """ffmpeg/ffprobe ran but could not read or decode the input."""


@dataclass(frozen=True)
class VideoProbe:
    """Stored (coded) dimensions plus the display rotation in degrees.

    ``rotation`` is normalised to one of 0/90/180/270 (a phone clip shot in
    portrait is typically stored 1920x1080 with rotation 90).
    """

    width: int
    height: int
    duration_s: float | None
    rotation: int = 0

    @property
    def display_width(self) -> int:
        return self.height if self.rotation in (90, 270) else self.width

    @property
    def display_height(self) -> int:
        return self.width if self.rotation in (90, 270) else self.height


def ffmpeg_available(*, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe") -> bool:
    """True when BOTH binaries resolve on PATH (never raises)."""
    return shutil.which(ffmpeg_bin) is not None and shutil.which(ffprobe_bin) is not None


def _run(cmd: list[str], *, timeout: int, binary: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise FfmpegNotInstalled(
            f"`{binary}` not found on PATH — build the product image FROM "
            "noctus-seed-backend-media-base (seed/docker/Dockerfile.backend-base "
            "target 'media') or install ffmpeg"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaProbeError(f"`{binary}` timed out after {timeout}s") from exc


def _stderr(res: subprocess.CompletedProcess[bytes]) -> str:
    return res.stderr.decode("utf-8", "replace").strip()[:300]


def _rotation(stream: dict) -> int:
    raw: float | None = None
    for side in stream.get("side_data_list") or []:
        if "rotation" in side:
            raw = side["rotation"]
            break
    if raw is None:
        tag = (stream.get("tags") or {}).get("rotate")
        if tag is not None:
            raw = tag
    if raw is None:
        return 0
    try:
        # ffprobe reports display-matrix rotation counter-clockwise (-90 ==
        # a clip to be shown rotated 90 clockwise); only the axis swap
        # matters for orientation, so fold to 0/90/180/270.
        return int(round(float(raw))) % 360 // 90 * 90
    except (TypeError, ValueError):
        return 0


def probe_video(path: str | Path, *, ffprobe_bin: str = "ffprobe") -> VideoProbe:
    """Probe the first video stream: stored size, duration, display rotation."""
    p = Path(path)
    res = _run(
        [ffprobe_bin, "-v", "error", "-select_streams", "v:0",
         "-show_entries",
         "stream=width,height:stream_side_data=rotation:stream_tags=rotate:format=duration",
         "-of", "json", str(p)],
        timeout=_PROBE_TIMEOUT_S, binary=ffprobe_bin,
    )
    if res.returncode != 0:
        raise MediaProbeError(f"ffprobe failed on {p.name}: {_stderr(res)}")
    try:
        data = json.loads(res.stdout.decode("utf-8"))
    except ValueError as exc:
        raise MediaProbeError(f"ffprobe returned unparseable output for {p.name}") from exc
    streams = data.get("streams") or []
    if not streams:
        raise MediaProbeError(f"no video stream in {p.name}")
    stream = streams[0]
    width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise MediaProbeError(f"video stream of {p.name} has no dimensions")
    duration: float | None
    try:
        duration = float((data.get("format") or {})["duration"])
    except (KeyError, TypeError, ValueError):
        duration = None
    return VideoProbe(width=width, height=height, duration_s=duration, rotation=_rotation(stream))


def orientation(probe: VideoProbe) -> Orientation:
    """Display orientation (rotation-aware): wider -> landscape, taller -> portrait."""
    w, h = probe.display_width, probe.display_height
    if w > h:
        return "landscape"
    if h > w:
        return "portrait"
    return "square"


def extract_frames(
    path: str | Path,
    positions: Sequence[float],
    max_px: int = 1280,
    *,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> list[bytes]:
    """One JPEG still per ``positions`` entry (fraction of duration, 0..1).

    ``max_px`` caps the LONGER edge (aspect kept, never upscaled). Frames are
    piped from ffmpeg — no temp files. Raises `MediaProbeError` if any frame
    cannot be produced; never returns a short list.
    """
    p = Path(path)
    duration = probe_video(p, ffprobe_bin=ffprobe_bin).duration_s or 0.0
    scale = (
        f"scale='if(gt(iw,ih),min({max_px},iw),-2)':'if(gt(iw,ih),-2,min({max_px},ih))'"
    )
    frames: list[bytes] = []
    for frac in positions:
        res = _run(
            [ffmpeg_bin, "-v", "error", "-ss", f"{max(duration * frac, 0.0):.2f}",
             "-i", str(p), "-frames:v", "1", "-vf", scale, "-q:v", "3",
             "-f", "mjpeg", "pipe:1"],
            timeout=_FRAME_TIMEOUT_S, binary=ffmpeg_bin,
        )
        if res.returncode != 0 or not res.stdout:
            raise MediaProbeError(
                f"ffmpeg could not extract a frame at {frac:.2f} of {p.name}: {_stderr(res)}"
            )
        frames.append(res.stdout)
    return frames


def extract_audio(
    source: bytes | str | Path,
    *,
    suffix: str = ".mp4",
    ffmpeg_bin: str = "ffmpeg",
) -> bytes:
    """Audio track as ogg/opus, mono 16 kHz (Whisper-friendly).

    ``source`` is a path or the raw video bytes (spooled to a temp file —
    mp4 needs a seekable input; ``suffix`` is only a demuxer hint). Raises
    `MediaProbeError` when there is no audio stream or it cannot be decoded.
    """
    def _encode(src: Path) -> bytes:
        res = _run(
            [ffmpeg_bin, "-v", "error", "-i", str(src), "-vn", "-ac", "1",
             "-ar", "16000", "-c:a", "libopus", "-f", "ogg", "pipe:1"],
            timeout=_AUDIO_TIMEOUT_S, binary=ffmpeg_bin,
        )
        if res.returncode != 0 or not res.stdout:
            raise MediaProbeError(f"ffmpeg could not extract audio: {_stderr(res)}")
        return res.stdout

    if isinstance(source, (str, Path)):
        return _encode(Path(source))
    with tempfile.TemporaryDirectory(prefix="noctus-media-") as tmp:
        src = Path(tmp) / f"input{suffix}"
        src.write_bytes(source)
        return _encode(src)


__all__ = [
    "FfmpegNotInstalled",
    "MediaProbeError",
    "Orientation",
    "VideoProbe",
    "extract_audio",
    "extract_frames",
    "ffmpeg_available",
    "orientation",
    "probe_video",
]
