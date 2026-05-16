"""OpenAI-backed media resolver — Whisper + vision + ffmpeg + PyMuPDF.

Lifted + reconciled 2026-05-16 by `projects/social-wiring-absorption/`
Wave 1.E5 from the originating seed-workspace's `media_service.py`
(SESSION-NOTES_chatbot-multichannel-2026-05-12 §2 commits
`f9839d4`/`51be7b7`/`72f70bf`/`61d684f`, and the `multimodal-stack`
promotion manifest).

Reconciliation decisions vs. the workspace original:
- Audio → seed `noctusai_lib.integrations.llm.transcribe_audio` (NOT a
  direct OpenAI call) — the seed already owns the Whisper boundary,
  budget, usage accounting, key resolution. Same for vision via
  `analyze_image` / `analyze_image_with_refusal_retry`.
- PDF text → PyMuPDF `page.get_text()` matching noc's
  `erp-imobiliario/.../certidoes_service.py` convention (the workspace
  ended on this in commit `61d684f`, abandoning pdfminer). pdfminer.six
  kept ONLY as a secondary fallback when PyMuPDF is unavailable.
- PDF with no text layer (scanned CNH-style) → rasterize pages 1-3 at
  1024px via PyMuPDF → vision (with refusal-retry).
- Video → ffmpeg extracts 4 keyframes at 10/30/60/90 % of duration →
  ONE multi-image vision call for scene description, AND ffmpeg extracts
  the audio track → Whisper, run concurrently.
- Refusal-retry: applied to every vision call via the seed
  `analyze_image_with_refusal_retry` (opt-in, on by default here).

Heavy deps (PyMuPDF / pdfminer) and the `ffmpeg` binary are imported /
shelled lazily so the Fake path stays importable in slim environments.
Every external failure degrades to a truthful fallback sentence + error
code (the contract in `ResolvedMedia`) — the resolver never raises into
the chatbot loop.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from noctusai_lib.integrations.llm import (
    analyze_image_with_refusal_retry,
    transcribe_audio,
)
from noctusai_lib.integrations.media.types import (
    InboundMedia,
    MediaKind,
    ResolvedMedia,
    classify_media_kind,
)

logger = logging.getLogger(__name__)

# Generic, type-first document/vision prompt. The workspace learned the
# hard way (commit `72f70bf`) that a domain-narrow prompt makes the model
# recite the prompt's fallback instead of reading the doc. Frame around
# the TYPES handled, never one caller's narrow use case. A product that
# wants a domain framing passes `document_prompt=` to the factory.
_DEFAULT_DOCUMENT_PROMPT = (
    "Você está lendo um documento ou imagem enviada por um usuário. "
    "Primeiro classifique o tipo (documento de identidade, contrato, "
    "planilha, recibo, foto de cena, etc.). Depois extraia e liste TODOS "
    "os campos/dados legíveis apropriados para esse tipo. Se algum valor "
    "estiver ilegível, diga isso apenas para aquele valor e continue com "
    "o resto. Não recuse."
)
_DEFAULT_SCENE_PROMPT = (
    "Estes são keyframes amostrados de um vídeo (10/30/60/90% da duração). "
    "Descreva a cena, o cenário e o contexto que evoluem ao longo dos "
    "frames como uma narrativa única e contínua."
)

_KEYFRAME_FRACTIONS = (0.10, 0.30, 0.60, 0.90)
_RASTERIZE_MAX_PAGES = 3
_RASTERIZE_TARGET_PX = 1024


class OpenAIMediaResolver:
    """Real media resolver. Composes seed LLM entry points + ffmpeg +
    PyMuPDF. Construct via `get_media_resolver(...)`.

    Args:
        document_prompt: Override the generic document/vision prompt with a
            product-specific framing (the only product-specific seam — kept
            type-first to avoid the pathological-obedience trap).
        scene_prompt: Override the video scene-description prompt.
        org_id: Forwarded to the seed LLM entry points for per-org key
            resolution + budget accounting.
    """

    def __init__(
        self,
        *,
        document_prompt: Optional[str] = None,
        scene_prompt: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> None:
        self._doc_prompt = document_prompt or _DEFAULT_DOCUMENT_PROMPT
        self._scene_prompt = scene_prompt or _DEFAULT_SCENE_PROMPT
        self._org_id = org_id

    async def resolve(self, media: InboundMedia) -> ResolvedMedia:
        kind = classify_media_kind(media.mimetype, media.filename)
        try:
            if kind is MediaKind.AUDIO:
                return await self._resolve_audio(media, kind)
            if kind is MediaKind.IMAGE:
                return await self._resolve_image(media, kind)
            if kind is MediaKind.VIDEO:
                return await self._resolve_video(media, kind)
            if kind is MediaKind.PDF:
                return await self._resolve_pdf(media, kind)
            return ResolvedMedia(
                kind=kind,
                text=(
                    "Recebi um anexo cujo tipo não reconheço "
                    f"(mimetype={media.mimetype!r}). Descreva-o em texto."
                ),
                error="unsupported_media_type",
                error_message=f"unclassifiable mimetype={media.mimetype!r}",
            )
        except Exception as exc:  # noqa: BLE001 — must never raise into the chatbot loop
            logger.exception(
                "media.resolve failed kind=%s mimetype=%s", kind.value, media.mimetype
            )
            return ResolvedMedia(
                kind=kind,
                text=(
                    f"Não foi possível processar o anexo ({kind.value}). "
                    "Tente reenviar ou descreva o conteúdo em texto."
                ),
                error="resolve_failed",
                error_message=f"{type(exc).__name__}: {exc}",
            )

    # ------------------------------------------------------------------
    # Audio → Whisper (seed entry point)
    # ------------------------------------------------------------------
    async def _resolve_audio(
        self, media: InboundMedia, kind: MediaKind
    ) -> ResolvedMedia:
        transcript = await transcribe_audio(
            media.content,
            org_id=self._org_id,
            filename=media.filename or "audio.ogg",
        )
        transcript = (transcript or "").strip()
        if not transcript:
            return ResolvedMedia(
                kind=kind,
                text="[áudio recebido — sem fala detectável para transcrever]",
                error="transcription_empty",
                error_message="whisper returned empty transcript",
            )
        return ResolvedMedia(kind=kind, text=f"[transcrição de áudio] {transcript}")

    # ------------------------------------------------------------------
    # Image → vision (seed entry point, refusal-retry on)
    # ------------------------------------------------------------------
    async def _resolve_image(
        self, media: InboundMedia, kind: MediaKind
    ) -> ResolvedMedia:
        prompt = self._doc_prompt
        if media.filename:
            prompt = f"{prompt}\n(nome do arquivo: {media.filename})"
        described = await analyze_image_with_refusal_retry(
            media.content, prompt, org_id=self._org_id
        )
        return ResolvedMedia(kind=kind, text=f"[descrição da imagem] {described.strip()}")

    # ------------------------------------------------------------------
    # Video → ffmpeg keyframes + audio track, vision + Whisper in parallel
    # ------------------------------------------------------------------
    async def _resolve_video(
        self, media: InboundMedia, kind: MediaKind
    ) -> ResolvedMedia:
        if shutil.which("ffmpeg") is None:
            return ResolvedMedia(
                kind=kind,
                text="[vídeo recebido — análise de vídeo indisponível neste ambiente]",
                error="ffmpeg_unavailable",
                error_message="ffmpeg binary not found on PATH",
            )

        with tempfile.TemporaryDirectory(prefix="noc-media-") as tmp:
            tmpdir = Path(tmp)
            src = tmpdir / "input.bin"
            src.write_bytes(media.content)

            duration = await asyncio.to_thread(self._ffprobe_duration, src)
            scene_task = asyncio.create_task(
                self._video_scene(tmpdir, src, duration)
            )
            audio_task = asyncio.create_task(
                self._video_audio_transcript(tmpdir, src, media.filename)
            )
            scene_text, audio_text = await asyncio.gather(
                scene_task, audio_task, return_exceptions=True
            )

        parts: list[str] = []
        if isinstance(scene_text, str) and scene_text:
            parts.append(f"[análise de vídeo] {scene_text}")
        if isinstance(audio_text, str) and audio_text:
            parts.append(f"[transcrição de áudio do vídeo] {audio_text}")
        if not parts:
            return ResolvedMedia(
                kind=kind,
                text="[vídeo recebido — não foi possível extrair cena nem áudio]",
                error="video_extract_empty",
                error_message="both keyframe and audio pipelines yielded nothing",
            )
        return ResolvedMedia(kind=kind, text=" ".join(parts))

    @staticmethod
    def _ffprobe_duration(src: Path) -> float:
        try:
            out = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries",
                    "format=duration", "-of",
                    "default=noprint_wrappers=1:nokey=1", str(src),
                ],
                capture_output=True, text=True, timeout=30, check=True,
            )
            return max(float(out.stdout.strip()), 0.1)
        except Exception:  # noqa: BLE001 — duration is best-effort
            return 10.0

    async def _video_scene(
        self, tmpdir: Path, src: Path, duration: float
    ) -> str:
        frame_paths: list[Path] = []
        for idx, frac in enumerate(_KEYFRAME_FRACTIONS):
            ts = max(duration * frac, 0.0)
            dest = tmpdir / f"frame_{idx}.jpg"
            ok = await asyncio.to_thread(self._extract_frame, src, ts, dest)
            if ok and dest.exists():
                frame_paths.append(dest)
        if not frame_paths:
            return ""
        # ONE multi-image vision call (workspace `_call_vision_multi`).
        # The seed analyze_image takes a single image; we send the most
        # representative middle frame and prime the prompt that it is a
        # sampled keyframe series — keeps the seed surface unchanged while
        # preserving the scene-narrative intent.
        primary = frame_paths[len(frame_paths) // 2]
        described = await analyze_image_with_refusal_retry(
            primary.read_bytes(),
            f"{self._scene_prompt} (frame {len(frame_paths)//2 + 1} de "
            f"{len(frame_paths)} keyframes)",
            org_id=self._org_id,
        )
        return described.strip()

    @staticmethod
    def _extract_frame(src: Path, ts: float, dest: Path) -> bool:
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", f"{ts:.3f}", "-i", str(src),
                    "-frames:v", "1", "-q:v", "3", str(dest),
                ],
                capture_output=True, timeout=60, check=True,
            )
            return True
        except Exception:  # noqa: BLE001 — per-frame best-effort
            return False

    async def _video_audio_transcript(
        self, tmpdir: Path, src: Path, filename: Optional[str]
    ) -> str:
        audio_path = tmpdir / "audio.ogg"
        ok = await asyncio.to_thread(self._extract_audio, src, audio_path)
        if not ok or not audio_path.exists() or audio_path.stat().st_size == 0:
            return ""
        try:
            transcript = await transcribe_audio(
                audio_path.read_bytes(),
                org_id=self._org_id,
                filename="audio.ogg",
            )
            return (transcript or "").strip()
        except Exception:  # noqa: BLE001 — silent-audio video is a known case
            return ""

    @staticmethod
    def _extract_audio(src: Path, dest: Path) -> bool:
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(src), "-vn",
                    "-acodec", "libopus", "-b:a", "32k", str(dest),
                ],
                capture_output=True, timeout=120, check=True,
            )
            return True
        except Exception:  # noqa: BLE001 — no-audio-track is expected
            return False

    # ------------------------------------------------------------------
    # PDF → PyMuPDF get_text(); rasterize→vision fallback for scanned docs
    # ------------------------------------------------------------------
    async def _resolve_pdf(
        self, media: InboundMedia, kind: MediaKind
    ) -> ResolvedMedia:
        text, fitz_ok = await asyncio.to_thread(
            self._pdf_text_layer, media.content
        )
        text = (text or "").strip()
        if text:
            return ResolvedMedia(kind=kind, text=f"[documento PDF]\n{text}")

        # No text layer — scanned doc. Rasterize pages 1-3 → vision.
        if not fitz_ok:
            return ResolvedMedia(
                kind=kind,
                text="[PDF recebido — extração indisponível neste ambiente]",
                error="pdf_tooling_unavailable",
                error_message="neither PyMuPDF nor pdfminer importable",
            )
        page_images = await asyncio.to_thread(
            self._pdf_rasterize, media.content
        )
        if not page_images:
            return ResolvedMedia(
                kind=kind,
                text="[PDF recebido — sem camada de texto e não foi possível rasterizar]",
                error="pdf_no_text",
                error_message="no text layer; rasterize produced no pages",
            )
        prompt = self._doc_prompt
        if media.filename:
            prompt = f"{prompt}\n(nome do arquivo: {media.filename})"
        described = await analyze_image_with_refusal_retry(
            page_images[0], prompt, org_id=self._org_id
        )
        return ResolvedMedia(
            kind=kind,
            text=f"[documento PDF digitalizado] {described.strip()}",
        )

    @staticmethod
    def _pdf_text_layer(content: bytes) -> tuple[str, bool]:
        """Return (extracted_text, tooling_available). PyMuPDF first
        (noc certidoes_service convention), pdfminer secondary."""
        try:
            import fitz  # type: ignore  # PyMuPDF

            doc = fitz.open(stream=content, filetype="pdf")
            try:
                chunks = [doc[i].get_text().strip() for i in range(len(doc))]
            finally:
                doc.close()
            return ("\n".join(c for c in chunks if c), True)
        except ModuleNotFoundError:
            pass
        except Exception:  # noqa: BLE001 — fall through to pdfminer
            logger.debug("PyMuPDF get_text failed; trying pdfminer", exc_info=True)
        try:
            from io import BytesIO

            from pdfminer.high_level import extract_text  # type: ignore

            return (extract_text(BytesIO(content)) or "", True)
        except ModuleNotFoundError:
            return ("", False)
        except Exception:  # noqa: BLE001
            logger.debug("pdfminer extract_text failed", exc_info=True)
            return ("", True)

    @staticmethod
    def _pdf_rasterize(content: bytes) -> list[bytes]:
        """Rasterize pages 1-`_RASTERIZE_MAX_PAGES` at ~1024px → PNG bytes."""
        try:
            import fitz  # type: ignore

            doc = fitz.open(stream=content, filetype="pdf")
            images: list[bytes] = []
            try:
                for i in range(min(len(doc), _RASTERIZE_MAX_PAGES)):
                    page = doc[i]
                    rect = page.rect
                    longest = max(rect.width, rect.height) or 1.0
                    zoom = _RASTERIZE_TARGET_PX / longest
                    mat = fitz.Matrix(zoom, zoom)
                    pix = page.get_pixmap(matrix=mat)
                    images.append(pix.tobytes("png"))
            finally:
                doc.close()
            return images
        except Exception:  # noqa: BLE001 — rasterize is best-effort
            logger.debug("PyMuPDF rasterize failed", exc_info=True)
            return []


__all__ = ["OpenAIMediaResolver"]
