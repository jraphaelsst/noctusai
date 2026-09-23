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

🔴 RENAMED 2026-09-20: `OpenAIMediaResolver` → `RealMediaResolver`.
-------------------------------------------------------------------
This class now accepts a `provider=` override (any
`documents.transcription.OCR_MODELS` key — `"openai"` / `"anthropic"` /
`"gemini"`), the fix for the 2026-09-18 incident where an org's
`llm_vision_provider="anthropic"` setting was silently ignored by every
document/vision call this resolver makes, while OpenAI's account sat at
zero credit. An `OpenAI`-prefixed name lying about being single-vendor is
exactly the kind of drift `check_canonical_organ_consumption`-adjacent
naming discipline exists to catch. Renamed rather than left undocumented,
mirroring the sibling `RealImagingAdapter` in
`integrations/imaging/real_adapter.py` (same `real_adapter.py` filename
convention, same vendor-neutral `Real<Domain>Adapter` shape).
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.integrations.llm import (
    analyze_image_with_refusal_retry,
    transcribe_audio,
)
from noctusai_lib.integrations.llm.exceptions import LLMNotConfigured
from noctusai_lib.integrations.media.types import (
    InboundMedia,
    MediaKind,
    ResolvedMedia,
    classify_media_kind,
)

logger = logging.getLogger(__name__)

#: `(image, prompt, **kwargs) -> description`, the shape
#: `analyze_image_with_refusal_retry` already has. Bound-default DI seam
#: (`KB § PATTERNS/backend/di-test-seam.md` Class-B) — a test injects a
#: fake analyzer instead of patching this module's imported name.
AnalyzeFn = Callable[..., Awaitable[str]]

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

#: Default page cap for rasterize→vision. Three is right for the documents
#: this resolver was built for (an ID card, a one-page comprovante): it bounds
#: the vision bill on a long PDF nobody meant to send.
#:
#: 🔴 IT IS WRONG FOR ANY DOCUMENT WHOSE CORRECTION LIVES AT THE END.
#: A certidão de casamento states the marriage on page 1 and its AVERBAÇÃO —
#: the divorce, the name change — on a later page. Truncating such a document
#: does not lose detail; it inverts the answer, and reads as a confident
#: "casado, comunhão parcial" for someone who has been divorced for years.
#: Callers that read those pass `max_pages=None` for no cap.
#:
#: 🔴 THIS ONLY BOUNDS VISION SPEND — IT NO LONGER BOUNDS WHICH PAGES ARE
#: READ. Before 2026-09-20, `_resolve_pdf` rasterized up to this many pages
#: and then described ONLY `page_images[0]` — every scanned PDF, regardless
#: of `max_pages`, effectively read page 1 alone. It now delegates to
#: `documents.make_document_transcriber`, whose `max_vision_pages` this
#: value feeds: pages with a real text layer are still read for free, and
#: up to this many of the REMAINING pages get a vision call, in order.
_RASTERIZE_MAX_PAGES = 3


class RealMediaResolver:
    """Real media resolver. Composes seed LLM entry points + ffmpeg +
    PyMuPDF. Construct via `get_media_resolver(...)`.

    Args:
        document_prompt: Override the generic document/vision prompt with a
            product-specific framing (the only product-specific seam — kept
            type-first to avoid the pathological-obedience trap).
        scene_prompt: Override the video scene-description prompt.
        org_id: Forwarded to the seed LLM entry points for per-org key
            resolution + budget accounting.
        provider: Which vendor answers a vision call — any key of
            `documents.providers.OCR_MODELS`. `None` (the default) resolves
            to `DEFAULT_DOCUMENT_PROVIDER` (Anthropic) — every caller of
            this resolver reads documents. A non-OpenAI provider always
            gets paired with that provider's OCR_MODELS pin — never the
            OpenAI-tuned default model, which is not portable across
            vendors (see `OCR_MODELS`'s own docstring).
        analyze: Test seam — bound default `analyze_image_with_refusal_retry`
            (`KB § PATTERNS/backend/di-test-seam.md` Class-B).
        render_dpi_policy: `None` (the default) leaves the PDF-transcription
            rung's own default render DPI unchanged — every existing
            consumer of this resolver (media generation, matrícula,
            certidão-estrutura) is unaffected. Forwarded verbatim to
            `documents.make_document_transcriber` when set — see
            `documents.transcription.RenderDpiPolicy`. Typed `Any` here (not
            `RenderDpiPolicy`) so importing this module never drags in
            `documents.transcription`.
    """

    def __init__(
        self,
        *,
        document_prompt: Optional[str] = None,
        scene_prompt: Optional[str] = None,
        org_id: Optional[str] = None,
        max_pages: Optional[int] = _RASTERIZE_MAX_PAGES,
        provider: Optional[str] = None,
        analyze: Optional[AnalyzeFn] = None,
        document_transcriber: Optional[Any] = None,
        render_dpi_policy: Optional[Any] = None,
    ) -> None:
        self._doc_prompt = document_prompt or _DEFAULT_DOCUMENT_PROMPT
        self._scene_prompt = scene_prompt or _DEFAULT_SCENE_PROMPT
        self._org_id = org_id
        # `None` = every page. Explicitly distinct from the default, so a
        # caller reading averbações opts IN to the bill rather than inheriting
        # a truncation it cannot see.
        self._max_pages = max_pages
        # `None` = "not specified" → the seed's canonical DOCUMENT provider
        # (`documents.providers.DEFAULT_DOCUMENT_PROVIDER`, Anthropic since
        # 2026-09-22). Every caller of this resolver reads documents (the
        # identity / matrícula ladder), so the process-wide chat default
        # (`LLMConfig.default_provider`, still "openai") is the wrong answer
        # here — an org that chose nothing used to be read by a vendor with
        # no credit. An EXPLICIT provider is forwarded verbatim; nothing here
        # fails over. Imported lazily: `documents` must not load at import.
        from noctusai_lib.integrations.documents.providers import (
            DEFAULT_DOCUMENT_PROVIDER,
        )

        self._provider = provider or DEFAULT_DOCUMENT_PROVIDER
        self._analyze: AnalyzeFn = analyze or analyze_image_with_refusal_retry
        # Injected in tests; built lazily otherwise (see
        # `_get_document_transcriber`) so importing this module never drags
        # in `documents.transcription`'s own dependency graph.
        self._document_transcriber = document_transcriber
        # `None` = the transcriber's own default render DPI, unchanged —
        # see the constructor docstring's `render_dpi_policy` entry.
        self._render_dpi_policy = render_dpi_policy

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
        except LLMNotConfigured as exc:
            # The selected vendor has no key. Named, not folded into the
            # generic `resolve_failed`: the operator's fix is "configure THIS
            # key", and a silent swap to another vendor is forbidden (manual
            # switch). Same code the transcriber's pre-check returns.
            # `exc` names the vendor itself — for audio that is the Whisper
            # vendor, not `self._provider` (vision only), so it is not
            # re-derived here.
            logger.warning("media.resolve: missing credential kind=%s: %s", kind.value, exc)
            return ResolvedMedia(
                kind=kind,
                text=(
                    f"Não foi possível processar o anexo ({kind.value}) — "
                    "provedor de IA não configurado."
                ),
                error="missing_credentials",
                error_message=str(exc),
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
        described = await self._analyze(
            media.content,
            prompt,
            provider=self._provider,
            model=self._model_for_provider(),
            org_id=self._org_id,
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
        described = await self._analyze(
            primary.read_bytes(),
            f"{self._scene_prompt} (frame {len(frame_paths)//2 + 1} de "
            f"{len(frame_paths)} keyframes)",
            provider=self._provider,
            model=self._model_for_provider(),
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
    # PDF → PyMuPDF get_text(); page-complete transcription for scanned docs
    # ------------------------------------------------------------------
    async def _resolve_pdf(
        self, media: InboundMedia, kind: MediaKind
    ) -> ResolvedMedia:
        camada = await asyncio.to_thread(self._pdf_text_layer, media.content)
        fitz_ok = camada.tooling_available
        # `is_substantive`, not "is non-empty": a scanned document carries a
        # digital-signature stamp in its text layer, and forwarding that to
        # the chatbot as the document's contents is worse than saying nothing.
        #
        # `media.force_vision` overrides this even when substantive — see its
        # own docstring (`media.types.InboundMedia`). Without the override, a
        # caller retrying because THIS SAME text carried none of the fields
        # it needed gets THIS SAME text back, silently: the classifier has
        # no way to know a downstream field-reader already rejected it.
        if camada.is_substantive and not media.force_vision:
            return ResolvedMedia(kind=kind, text=f"[documento PDF]\n{camada.text}")

        if not fitz_ok:
            return ResolvedMedia(
                kind=kind,
                text="[PDF recebido — extração indisponível neste ambiente]",
                error="pdf_tooling_unavailable",
                error_message="neither PyMuPDF nor pdfminer importable",
            )

        # No text layer — scanned doc. EVERY page can matter: an averbação
        # (a divorce, a name change) can sit on a LATER page than this
        # resolver would otherwise ever rasterize, and truncating does not
        # lose detail — it returns the opposite answer (see
        # `_RASTERIZE_MAX_PAGES`). Delegating to the seed's page-complete
        # transcriber — rather than rasterizing here and describing only
        # the first image — is what fixes that: it reads every page up to
        # its own cap, brings the correct provider→model pairing, and
        # classifies a quota failure instead of a generic one.
        transcricao = await self._get_document_transcriber().transcribe(
            media.content,
            mimetype=media.mimetype,
            filename=media.filename,
            force_vision=media.force_vision,
        )
        if not transcricao.ok:
            return ResolvedMedia(
                kind=kind,
                text=(
                    "[PDF recebido — não foi possível transcrever as páginas "
                    f"digitalizadas ({transcricao.error})]"
                ),
                error=transcricao.error,
                error_message=transcricao.error_message,
            )
        texto = transcricao.text.strip()
        if not texto:
            return ResolvedMedia(
                kind=kind,
                text="[PDF recebido — sem texto legível nas páginas digitalizadas]",
                error="pdf_no_text",
                error_message="scanned pages produced no readable text",
            )
        return ResolvedMedia(
            kind=kind,
            text=f"[documento PDF digitalizado] {texto}",
        )

    @staticmethod
    def _pdf_text_layer(content: bytes):
        """Return the per-page `PdfTextLayer` classification.

        Single-sourced 2026-05-19 to the public
        `noctusai_lib.integrations.media.pdf_text` module — same PyMuPDF-first
        / pdfminer-fallback logic, now also consumed by
        `DriveFileContent.text` for `application/pdf` (Phase 6a-drive).
        Upgraded to the classifier so the caller can tell a real text layer
        from a signature stamp printed over a scan."""
        from noctusai_lib.integrations.media.pdf_text import (
            classify_pdf_text_layer,
        )

        return classify_pdf_text_layer(content)

    def _get_document_transcriber(self):
        """The page-complete transcriber `_resolve_pdf` delegates to for a
        scanned document. Injected in tests; built lazily otherwise so
        importing this module never drags in `documents.transcription`'s
        own dependency graph for a caller who only ever resolves
        audio/image/video.

        `max_vision_pages` mirrors `self._max_pages`: `None` keeps the
        transcriber's own generous safety cap (`MAX_VISION_PAGES`, pages
        NEEDING vision — free text-layer pages are unlimited either way);
        a concrete N (the resolver's own default of 3) caps vision spend at
        N pages rather than, as before this delegation existed, silently
        describing page 1 alone regardless of N.
        """
        if self._document_transcriber is None:
            from noctusai_lib.integrations.documents.transcription import (
                MAX_VISION_PAGES,
                make_document_transcriber,
            )

            kwargs: dict[str, Any] = {
                "real": True,
                "org_id": self._org_id,
                "provider": self._provider,
            }
            if self._max_pages is not None:
                kwargs["max_vision_pages"] = self._max_pages
            else:
                kwargs["max_vision_pages"] = MAX_VISION_PAGES
            # `None` is `make_document_transcriber`'s own default — passing
            # it verbatim keeps every consumer that never set this
            # unaffected (`render_dpi` stays in sole charge there).
            kwargs["render_dpi_policy"] = self._render_dpi_policy
            self._document_transcriber = make_document_transcriber(**kwargs)
        return self._document_transcriber

    def _model_for_provider(self) -> Optional[str]:
        """The OCR model paired with `self._provider`, or `None`.

        `None` when `self._provider` is `"openai"` — that keeps
        `analyze_image`'s own default (`LLMConfig.default_vision_model`,
        `gpt-4o`), unchanged, for an org that explicitly picked OpenAI.
        (An unset provider no longer exists here: `__init__` resolves it to
        the canonical document provider.)

        A NON-OpenAI provider has no such tuned default at this layer, so
        this borrows the seed's canonical per-provider OCR pin
        (`documents.transcription.OCR_MODELS` — the SAME pin
        `make_document_transcriber` uses for the PDF rung) rather than
        sending an OpenAI-only model name to a different vendor's API,
        which is a 404, not a degraded answer.
        """
        if self._provider == "openai":
            return None
        from noctusai_lib.integrations.documents.providers import OCR_MODELS

        return OCR_MODELS.get(self._provider)


__all__ = ["RealMediaResolver"]
