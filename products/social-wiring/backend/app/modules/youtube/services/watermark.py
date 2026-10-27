"""Logo-watermark detection for exclusive-listing video folders.

An exclusive listing ships each video twice: one copy carrying the One
Consultoria logo watermark (ours — uploaded) and a clean copy sent to the
partner agencies (never uploaded). To tell them apart without "watching"
the videos we grab 1-3 still frames per candidate with ffmpeg and ask a
vision model, in ONE request per orientation group, which candidates show
the reference logo.

Seam: ``WatermarkDetector`` (Protocol) with ``VisionWatermarkDetector``
(ffmpeg + seed ``analyze_image``) as the Real and ``FakeWatermarkDetector``
for tests. ``WhatsAppIntakeService`` receives one via its constructor.

``pick_logo_version`` turns verdicts into a decision and NEVER guesses:
anything other than exactly one confident logo hit among otherwise clearly
logo-less candidates returns ``None`` → the caller asks the user.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Protocol, Sequence

from app.config import settings

logger = logging.getLogger(__name__)

LOGO_ASSET = Path(__file__).resolve().parents[3] / "assets" / "one_consultoria_logo.webp"

# A verdict below this confidence is treated as "not sure" (never a pick).
MIN_CONFIDENCE = 0.6
# Fractions of the video duration where stills are grabbed (1-3 frames).
FRAME_POSITIONS = (0.25, 0.6)
_FRAME_MAX_WIDTH = 768


class WatermarkDetectionError(Exception):
    """Detection could not be completed (no ffmpeg, vision/quota error, bad reply)."""


@dataclass(frozen=True)
class LogoVerdict:
    """Vision verdict for one video. ``has_logo=None`` = unusable/unknown."""

    has_logo: bool | None
    confidence: float = 0.0


class WatermarkDetector(Protocol):
    async def detect(self, videos: Sequence[Path]) -> list[LogoVerdict]:
        """One verdict per video, same order. Raises ``WatermarkDetectionError``."""
        ...


def pick_logo_version(verdicts: Sequence[LogoVerdict]) -> int | None:
    """Index of THE video carrying the logo, or ``None`` when not clear-cut.

    Clear-cut = exactly one confident ``has_logo=True`` and every other
    verdict a confident ``has_logo=False``.
    """
    positives = [
        i for i, v in enumerate(verdicts)
        if v.has_logo is True and v.confidence >= MIN_CONFIDENCE
    ]
    if len(positives) != 1:
        return None
    for i, v in enumerate(verdicts):
        if i == positives[0]:
            continue
        if v.has_logo is not False or v.confidence < MIN_CONFIDENCE:
            return None
    return positives[0]


# ─── Real detector ────────────────────────────────────────────────────


def _probe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise WatermarkDetectionError(f"ffprobe indisponível: {exc}") from exc
    if out.returncode != 0:
        raise WatermarkDetectionError(f"ffprobe falhou em {path.name}: {out.stderr[:200]}")
    try:
        return float(json.loads(out.stdout)["format"]["duration"])
    except (KeyError, ValueError, TypeError):
        return None


def extract_frames(path: Path, out_dir: Path, positions: Sequence[float] = FRAME_POSITIONS) -> list[bytes]:
    """Grab one JPEG still per position (fraction of duration) via ffmpeg."""
    duration = _probe_duration(path) or 0.0
    frames: list[bytes] = []
    for n, frac in enumerate(positions):
        target = out_dir / f"{path.stem}-{n}.jpg"
        cmd = [
            "ffmpeg", "-v", "error", "-y",
            "-ss", f"{max(duration * frac, 0.0):.2f}",
            "-i", str(path),
            "-frames:v", "1",
            "-vf", f"scale='min({_FRAME_MAX_WIDTH},iw)':-2",
            "-q:v", "3",
            str(target),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise WatermarkDetectionError(f"ffmpeg indisponível: {exc}") from exc
        if res.returncode != 0 or not target.exists():
            raise WatermarkDetectionError(
                f"ffmpeg falhou ao extrair frame de {path.name}: {res.stderr[:200]}"
            )
        frames.append(target.read_bytes())
    if not frames:
        raise WatermarkDetectionError(f"nenhum frame extraído de {path.name}")
    return frames


def _labels(n: int) -> list[str]:
    return [chr(ord("A") + i) for i in range(n)]


def build_prompt(frame_counts: Sequence[int]) -> str:
    lines = [
        "A primeira imagem é o LOGO DE REFERÊNCIA da One Consultoria Imobiliária: "
        "a palavra \"ONE\" em letras grandes cinza-chumbo, com um \"N\" formado por "
        "um bloco dourado/bege inclinado e uma faixa branca, e abaixo o texto "
        "\"CONSULTORIA IMOBILIÁRIA\" em letras finas.",
        "As imagens seguintes são frames (capturas de tela) de vídeos candidatos:",
    ]
    cursor = 2
    for label, count in zip(_labels(len(frame_counts)), frame_counts):
        lines.append(f"- Vídeo {label}: imagens {cursor} a {cursor + count - 1}")
        cursor += count
    lines.append(
        "Para CADA vídeo, diga se esse logo aparece sobreposto (marca d'água) em "
        "algum dos seus frames. Ignore logos de outras empresas, placas e textos "
        "que façam parte da cena. Responda SOMENTE com JSON, sem texto extra, no "
        'formato: {"videos":[{"id":"A","has_logo":true,"confidence":0.95}]} '
        "onde confidence vai de 0 a 1."
    )
    return "\n".join(lines)


def parse_verdicts(text: str, count: int) -> list[LogoVerdict]:
    """Defensively parse the model reply into ``count`` verdicts."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        raise WatermarkDetectionError("resposta do modelo sem JSON")
    try:
        data = json.loads(match.group(0))
        items = data["videos"]
    except (ValueError, KeyError, TypeError) as exc:
        raise WatermarkDetectionError(f"JSON inválido na resposta do modelo: {exc}") from exc
    by_id: dict[str, LogoVerdict] = {}
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            has_logo = item.get("has_logo")
            try:
                conf = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                conf = 0.0
            by_id[str(item.get("id", "")).strip().upper()] = LogoVerdict(
                has_logo=has_logo if isinstance(has_logo, bool) else None,
                confidence=min(max(conf, 0.0), 1.0),
            )
    return [by_id.get(label, LogoVerdict(None, 0.0)) for label in _labels(count)]


VisionFn = Callable[..., Awaitable[str]]


class VisionWatermarkDetector:
    """ffmpeg stills + one seed ``analyze_image`` request per group."""

    def __init__(self, *, model: str | None = None, vision_fn: VisionFn | None = None,
                 logo_path: Path = LOGO_ASSET):
        self._model = model or settings.watermark_vision_model
        self._vision_fn = vision_fn
        self._logo_path = logo_path

    async def detect(self, videos: Sequence[Path]) -> list[LogoVerdict]:
        if not self._logo_path.exists():
            raise WatermarkDetectionError(f"logo de referência ausente: {self._logo_path}")
        tmp = Path(tempfile.mkdtemp(prefix="wm-frames-"))
        try:
            per_video = [await asyncio.to_thread(extract_frames, v, tmp) for v in videos]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        images: list[bytes] = [self._logo_path.read_bytes()]
        for frames in per_video:
            images.extend(frames)
        prompt = build_prompt([len(f) for f in per_video])
        vision = self._vision_fn
        if vision is None:
            from noctusai_lib.integrations.llm import analyze_image as vision
        try:
            reply = await vision(images, prompt, provider="anthropic", model=self._model)
        except Exception as exc:  # provider/quota/network — surfaced, caller asks the user
            logger.warning("watermark vision call failed: %s", exc)
            raise WatermarkDetectionError(f"falha na análise de imagem: {exc}") from exc
        return parse_verdicts(str(reply), len(videos))


# ─── Fake (tests) ─────────────────────────────────────────────────────


class FakeWatermarkDetector:
    """Deterministic detector: verdicts by file name; records every call."""

    def __init__(self, logo_files: Sequence[str] = (), *, error: Exception | None = None,
                 verdicts: dict[str, LogoVerdict] | None = None):
        self._logo_files = set(logo_files)
        self._error = error
        self._verdicts = verdicts or {}
        self.calls: list[list[str]] = []

    async def detect(self, videos: Sequence[Path]) -> list[LogoVerdict]:
        self.calls.append([Path(v).name for v in videos])
        if self._error is not None:
            raise self._error
        out: list[LogoVerdict] = []
        for v in videos:
            name = Path(v).name
            out.append(self._verdicts.get(name) or LogoVerdict(name in self._logo_files, 0.95))
        return out
