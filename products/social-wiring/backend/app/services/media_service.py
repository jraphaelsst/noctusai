"""Multimodal inbound resolver.

The chatbot needs to read more than text. WhatsApp routinely delivers
voice notes, photos, videos, and documents; the platform chat does the
same for image attachments. This service turns each inbound media into
a text-form the OpenAI chatbot can reason about, so the user's
"transcribe this audio" / "describe this image" / "look at this PDF"
intents become first-class instead of "sorry, not supported here."

Pattern mirrors ``whatsapp-google-scheduling``: audio → Whisper via
``client.audio.transcriptions.create``; image → vision via
``chat.completions.create`` with an ``image_url`` content block. We
use the OpenAI SDK directly (same as ``ChatbotService``) rather than
going through ``noctusai_lib.integrations.llm`` to keep failure modes
local and avoid the LLMConfig singleton coupling.
"""
from __future__ import annotations

import base64
import logging
import mimetypes
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_IMAGE_PROMPT = (
    "Descreva esta imagem em pt-BR de forma objetiva e curta (no maximo 3 "
    "frases), focando em elementos uteis para um corretor de imoveis ou para "
    "um pedido de producao de conteudo. Inclua: tipo de comodo, fachada, "
    "planta, documento, dano visivel, exterior, ou qualquer texto legivel. "
    "Nao invente detalhes que nao estejam visiveis na imagem."
)

_DOCUMENT_PROMPT = (
    "Você está analisando uma OU MAIS páginas de um documento (podem ser "
    "imagens rasterizadas de um PDF). LEIA o que estiver visível e descreva "
    "em pt-BR de forma estruturada e útil. NUNCA diga que 'não foi possível "
    "extrair texto' — descreva o que você VÊ, mesmo que seja parcial.\n\n"
    "Identifique primeiro o TIPO de documento (CNH, RG, passaporte, "
    "contrato, escritura, matrícula de imóvel, IPTU, comprovante de "
    "endereço, fatura, ficha de visita, planta baixa, fotografia "
    "identitária, cartão de visita, etc.) e responda com este formato:\n\n"
    "Tipo: <tipo do documento>\n"
    "Resumo: <2 a 4 frases descrevendo o conteúdo geral>\n"
    "Dados visíveis:\n"
    "- <campo>: <valor>\n"
    "- <campo>: <valor>\n"
    "...\n\n"
    "Para um documento de identidade (CNH/RG/passaporte), liste: nome, "
    "documento (RG/CPF), data de nascimento, filiação, órgão emissor, "
    "validade, categoria.\n"
    "Para um documento imobiliário, liste: endereço, código do imóvel "
    "(ONExxxx se aparecer), valor, área, proprietário, datas relevantes.\n"
    "Para um documento financeiro, liste: emissor, beneficiário, valor, "
    "vencimento, código de barras.\n"
    "Para qualquer outro documento, liste os 5-10 campos mais relevantes "
    "que você consegue ler.\n\n"
    "Regras:\n"
    "- Transcreva o texto EXATAMENTE como aparece (não traduza, não invente).\n"
    "- Se um campo estiver borrado/cortado, marque como 'ilegível' mas NÃO "
    "  desista do documento inteiro.\n"
    "- Se houver foto da pessoa, mencione brevemente (ex.: 'foto 3x4 de "
    "  homem adulto').\n"
    "- NUNCA responda apenas 'não foi possível extrair texto'."
)

_VIDEO_FRAMES_PROMPT = (
    "Estes sao quadros amostrados em ordem cronologica de um video curto. "
    "Descreva em pt-BR, em 3 a 6 frases, o que esta acontecendo no video: "
    "cenario (ambiente, comodos, exterior, paisagem, urbano/rural), pessoas "
    "ou animais presentes, acoes principais, objetos/elementos relevantes "
    "para um corretor de imoveis ou um pedido de producao de conteudo, e "
    "qualquer mudanca importante entre os quadros. Nao invente detalhes "
    "que nao estejam visiveis."
)


@dataclass(frozen=True)
class ResolvedMedia:
    """Result of resolving an inbound media into a text-form the
    chatbot can reason about."""

    text: str
    """User-facing-style enriched text (e.g. ``[Audio transcrito] ola tudo bem?``).
    Fed directly to the chatbot's ``reply()`` as the inbound message."""

    media_type: str
    """Coarse type: ``audio`` / ``image`` / ``video`` / ``document`` / ``unknown``."""

    raw_text: str
    """The raw extracted text (transcript or description) without the
    user-facing prefix — kept for audit/log."""

    structured_payload: dict[str, Any]
    """Bag of metadata about the resolution: mimetype, transcript,
    description, error notes, original_url. Persisted into
    ``conversation_messages.structured_payload``."""

    trigger_reply: bool = True


class MediaService:
    """Per-request collaborator. Constructed with the WAHA base URL +
    api key (for media downloads) and an OpenAI key (for transcription
    + vision). Both come from ``SocialWiringSettings``."""

    def __init__(
        self,
        *,
        waha_base_url: str,
        waha_api_key: str,
        openai_api_key: str,
        audio_model: str = "gpt-4o-mini-transcribe",
        vision_model: str = "gpt-4o-mini",
    ):
        self._waha_base_url = waha_base_url.rstrip("/")
        self._waha_api_key = waha_api_key
        self._openai_api_key = openai_api_key
        self._audio_model = audio_model
        self._vision_model = vision_model

    # ─── Public entry points ───────────────────────────────────────────
    async def resolve_inbound(
        self,
        *,
        url: str | None,
        mimetype: str | None,
        filename: str | None = None,
        fallback_text: str = "",
    ) -> ResolvedMedia:
        """Download a WAHA-hosted media and resolve it to enriched text.

        Returns a ResolvedMedia. On any failure, ``raw_text`` carries an
        error note and ``trigger_reply`` is True (we still want the bot
        to acknowledge what arrived, not silently drop it).
        """
        mt = (mimetype or "").lower()
        try:
            media_bytes = await self._download(url) if url else None
        except Exception as exc:
            logger.exception("media download failed: %s", url)
            return ResolvedMedia(
                text=fallback_text or "[Anexo recebido — falha ao baixar]",
                media_type="unknown",
                raw_text="",
                structured_payload={
                    "media_type": "unknown",
                    "mimetype": mt,
                    "original_url": url,
                    "error": "download_failed",
                    "error_message": str(exc)[:300],
                },
            )

        if media_bytes is None:
            return ResolvedMedia(
                text=fallback_text or "[Anexo recebido sem URL — nao foi possivel processar]",
                media_type="unknown",
                raw_text="",
                structured_payload={
                    "media_type": "unknown",
                    "mimetype": mt,
                    "error": "missing_url",
                },
            )

        # Route by mimetype family.
        if mt.startswith("audio/"):
            return await self._resolve_audio(media_bytes, mimetype=mt, fallback_text=fallback_text)
        if mt.startswith("image/"):
            return await self._resolve_image(media_bytes, mimetype=mt, fallback_text=fallback_text)
        if mt.startswith("video/"):
            return await self._resolve_video(media_bytes, mimetype=mt, fallback_text=fallback_text)
        if mt == "application/pdf" or _looks_like_document(mt, filename):
            return await self._resolve_document(
                media_bytes, mimetype=mt, filename=filename, fallback_text=fallback_text,
            )
        return ResolvedMedia(
            text=fallback_text or f"[Anexo recebido — tipo nao suportado: {mt or 'desconhecido'}]",
            media_type="unknown",
            raw_text="",
            structured_payload={
                "media_type": "unknown",
                "mimetype": mt,
                "filename": filename,
                "size_bytes": len(media_bytes),
            },
        )

    async def transcribe_audio(self, audio_bytes: bytes, *, filename: str = "audio.ogg") -> str:
        """Public re-entry for callers that already have audio bytes
        (e.g. the platform chat router's direct upload). Returns the
        transcript text; never raises — returns "" on failure."""
        try:
            return await self._call_whisper(audio_bytes, filename=filename)
        except Exception:
            logger.exception("transcribe_audio failed")
            return ""

    async def describe_image(
        self,
        image_bytes: bytes,
        *,
        mimetype: str = "image/jpeg",
        prompt: str | None = None,
    ) -> str:
        """Public re-entry for image-bytes-in-hand callers."""
        try:
            return await self._call_vision(image_bytes, mimetype=mimetype, prompt=prompt or _IMAGE_PROMPT)
        except Exception:
            logger.exception("describe_image failed")
            return ""

    # ─── Resolvers per media family ────────────────────────────────────
    async def _resolve_audio(
        self, audio_bytes: bytes, *, mimetype: str, fallback_text: str
    ) -> ResolvedMedia:
        filename = _filename_for_mimetype(mimetype, default="audio.ogg")
        transcript = await self.transcribe_audio(audio_bytes, filename=filename)
        if not transcript:
            return ResolvedMedia(
                text=fallback_text or "[Audio recebido — transcricao indisponivel]",
                media_type="audio",
                raw_text="",
                structured_payload={
                    "media_type": "audio",
                    "mimetype": mimetype,
                    "error": "transcription_failed",
                },
            )
        return ResolvedMedia(
            text=f"[Audio transcrito] {transcript}",
            media_type="audio",
            raw_text=transcript,
            structured_payload={
                "media_type": "audio",
                "mimetype": mimetype,
                "transcript": transcript,
            },
        )

    async def _resolve_image(
        self, image_bytes: bytes, *, mimetype: str, fallback_text: str
    ) -> ResolvedMedia:
        description = await self.describe_image(image_bytes, mimetype=mimetype)
        if not description:
            return ResolvedMedia(
                text=fallback_text or "[Imagem recebida — descricao indisponivel]",
                media_type="image",
                raw_text="",
                structured_payload={
                    "media_type": "image",
                    "mimetype": mimetype,
                    "error": "description_failed",
                },
            )
        return ResolvedMedia(
            text=f"[Imagem] {description}",
            media_type="image",
            raw_text=description,
            structured_payload={
                "media_type": "image",
                "mimetype": mimetype,
                "description": description,
            },
        )

    async def _resolve_video(
        self, video_bytes: bytes, *, mimetype: str, fallback_text: str
    ) -> ResolvedMedia:
        """Video resolution = scene analysis + (best-effort) audio transcript.

        Two parallel goals:

        1. SCENE — extract 3-4 keyframes via ffmpeg, send them as image
           inputs to vision, get a textual description of what's
           happening (cenario, pessoas, acoes, objetos). This is the
           default useful signal even when the video has no speech
           (the pool/garden video the user sent earlier had ambient
           sound only).

        2. AUDIO — extract the audio track via ffmpeg + Whisper. Many
           videos have no speech; an empty transcript here is normal
           and we just omit the section from the output.

        We return enriched text that combines whatever we got. If BOTH
        signals fail we fall back to acknowledging the video without
        false claims about content.
        """
        input_ext = _ext_for(mimetype, ".mp4")

        # Run both extractions in parallel — they share temp files but
        # different output paths, no contention.
        import asyncio

        scene_description = ""
        audio_transcript = ""
        try:
            scene_description, audio_transcript = await asyncio.gather(
                self._describe_video_scene(video_bytes, input_ext=input_ext),
                self._transcribe_video_audio(video_bytes, input_ext=input_ext),
                return_exceptions=False,
            )
        except Exception:
            logger.exception("video resolve: parallel extraction failed")

        # Compose the enriched text from whichever signals worked.
        parts: list[str] = []
        if scene_description:
            parts.append(f"[Video — cena] {scene_description}")
        if audio_transcript:
            parts.append(f"[Video — audio transcrito] {audio_transcript}")
        combined = "\n\n".join(parts)

        if combined:
            return ResolvedMedia(
                text=combined,
                media_type="video",
                raw_text=combined,
                structured_payload={
                    "media_type": "video",
                    "mimetype": mimetype,
                    "size_bytes": len(video_bytes),
                    "scene_description": scene_description or None,
                    "audio_transcript": audio_transcript or None,
                },
            )
        return ResolvedMedia(
            text=fallback_text or "[Video recebido — nao foi possivel analisar]",
            media_type="video",
            raw_text="",
            structured_payload={
                "media_type": "video",
                "mimetype": mimetype,
                "size_bytes": len(video_bytes),
                "error": "scene_and_audio_failed",
            },
        )

    async def _transcribe_video_audio(self, video_bytes: bytes, *, input_ext: str) -> str:
        """Pull the audio track out of a video and run it through Whisper.

        Returns "" when the video has no speech or ffmpeg/Whisper fails —
        callers compose around the empty string."""
        try:
            audio_bytes = _extract_audio_via_ffmpeg(video_bytes, input_ext=input_ext)
            if audio_bytes:
                return await self.transcribe_audio(audio_bytes, filename="audio.ogg")
            # ffmpeg unavailable — try raw bytes (Whisper accepts mp4 directly)
            return await self.transcribe_audio(
                video_bytes, filename=f"video{input_ext}"
            )
        except Exception:
            logger.exception("video audio transcription failed")
            return ""

    async def _describe_video_scene(self, video_bytes: bytes, *, input_ext: str) -> str:
        """Sample keyframes from the video and ask vision to describe
        what's happening. Returns "" on any failure — callers compose
        around the empty string."""
        frames = _extract_keyframes_via_ffmpeg(video_bytes, input_ext=input_ext, count=4)
        if not frames:
            logger.info("video scene: no keyframes extracted (ffmpeg missing or failed)")
            return ""
        try:
            return await self._call_vision_multi(frames, prompt=_VIDEO_FRAMES_PROMPT)
        except Exception:
            logger.exception("video scene description failed")
            return ""

    async def _resolve_document(
        self,
        doc_bytes: bytes,
        *,
        mimetype: str,
        filename: str | None,
        fallback_text: str,
    ) -> ResolvedMedia:
        """Documents: extract text OR rasterize + vision, then summarize.

        Three-tier fallback for PDFs:
        1. ``pdfminer.six`` text extraction — fast, free, works for
           any PDF with an embedded text layer (most exported PDFs).
        2. If text extraction returns empty/too-short (typical of
           SCANNED PDFs like the user's CNH where the "text" is just
           a photo of paper), rasterize the first 1-3 pages via
           PyMuPDF and send the page images through vision. This
           recovers content from image-only PDFs that pdfminer can't
           read.
        3. If neither produces content, acknowledge the document
           without inventing details.

        Non-PDF office formats fall through to the rasterize attempt
        too — if PyMuPDF can open them (it supports many formats),
        we get something useful; otherwise we acknowledge politely.
        """
        logger.info(
            "document resolve: start filename=%r mimetype=%r size=%d",
            filename,
            mimetype,
            len(doc_bytes),
        )
        extracted_text = ""
        try:
            if mimetype == "application/pdf":
                # 🔴 STRIPPED, NOT RAW — the `< 200` threshold below has to
                # count characters the document actually SAYS.
                #
                # A cartório scan's text layer is a verification stamp
                # printed over the image, and it is long enough to clear
                # that threshold on its own: a 3-page ONR certidão carries
                # 137 chars/page (411 total) and a "Visualização de
                # Matrícula" 83 (249 total). Both would skip rasterize and
                # then be summarised — so the bot would answer with the
                # document's own validation link as its contents while the
                # scan was never read. Same defect as the matrícula
                # extractor's, same file, different threshold.
                #
                # `strip_provenance_stamps` leaves genuine prose untouched,
                # so a digitally-issued PDF still takes the free tier-1
                # path exactly as before.
                from noctusai_lib.integrations.media import strip_provenance_stamps

                extracted_text = strip_provenance_stamps(
                    _extract_pdf_text(doc_bytes)
                )
        except Exception:
            logger.exception("document resolve: pdf text extraction failed")

        # Tier 2: rasterize + vision when text is empty or thin (<200
        # chars suggests OCR-less scan).
        rasterized_summary = ""
        rasterize_attempted = False
        if len(extracted_text.strip()) < 200:
            rasterize_attempted = True
            try:
                page_images = _rasterize_pdf_pages(doc_bytes, max_pages=3, max_width=1024)
            except Exception:
                logger.exception("document resolve: pdf rasterization failed")
                page_images = []
            if page_images:
                # Filename gives the model a strong prior. e.g. "CNH..."
                # primes it to expect a driver's license.
                contextual_prompt = _DOCUMENT_PROMPT
                if filename:
                    contextual_prompt = (
                        f"Nome do arquivo: {filename}\n\n{contextual_prompt}"
                    )
                try:
                    rasterized_summary = await self._call_vision_multi(
                        page_images, prompt=contextual_prompt
                    )
                except Exception:
                    logger.exception("document resolve: vision summary failed")
                # Retry once with a more forceful directive when the model
                # returns a refusal shape ("não foi possível extrair"
                # etc.). Most refusals come from the model being too
                # cautious about partial reads — naming the documents we
                # successfully handle and forbidding the refusal phrase
                # tips it over.
                if _looks_like_refusal(rasterized_summary):
                    logger.info(
                        "document resolve: first vision pass refused — retrying with stronger directive"
                    )
                    retry_prompt = (
                        "Sua resposta anterior recusou ou disse que não "
                        "conseguiu ler. ISSO É INACEITÁVEL. Estas páginas "
                        "RASTERIZADAS estão totalmente legíveis para você "
                        "como modelo de visão. Mesmo que o documento seja "
                        "um cartão de identidade, foto, certificado, "
                        "cartão digital, ou qualquer outro item visual, "
                        "DESCREVA O QUE VOCÊ VÊ.\n\n" + contextual_prompt
                    )
                    try:
                        retry = await self._call_vision_multi(
                            page_images, prompt=retry_prompt
                        )
                        if retry and not _looks_like_refusal(retry):
                            rasterized_summary = retry
                    except Exception:
                        logger.exception("document resolve: retry vision failed")

        # Tier 1 summary (only when text was substantial).
        text_summary = ""
        if extracted_text.strip() and len(extracted_text.strip()) >= 200:
            text_summary = await self._summarize_document_text(extracted_text)
            logger.info(
                "document resolve: text-summary chars=%d (refusal=%s)",
                len(text_summary),
                _looks_like_refusal(text_summary),
            )
        else:
            logger.info(
                "document resolve: text extraction too thin (chars=%d); skipping text-summary path",
                len(extracted_text.strip()),
            )
        logger.info(
            "document resolve: rasterized_summary chars=%d (refusal=%s)",
            len(rasterized_summary),
            _looks_like_refusal(rasterized_summary),
        )

        # If text summary came back as a refusal, fall through to the
        # rasterized output (which used vision and may have worked).
        if text_summary and _looks_like_refusal(text_summary):
            logger.info("document resolve: text-summary was a refusal; preferring rasterized")
            text_summary = ""
        # If rasterized came back as a refusal, drop it too.
        if rasterized_summary and _looks_like_refusal(rasterized_summary):
            logger.info("document resolve: rasterized was a refusal; dropping")
            rasterized_summary = ""

        final_summary = text_summary or rasterized_summary
        if not final_summary:
            note = "no_text_extracted"
            if rasterize_attempted and not rasterized_summary:
                note = "rasterize_and_text_both_failed"
            return ResolvedMedia(
                text=(
                    fallback_text
                    or f"[Documento recebido: {filename or 'arquivo'} — nao consegui ler o conteudo]"
                ),
                media_type="document",
                raw_text="",
                structured_payload={
                    "media_type": "document",
                    "mimetype": mimetype,
                    "filename": filename,
                    "size_bytes": len(doc_bytes),
                    "extracted_chars": len(extracted_text),
                    "rasterize_attempted": rasterize_attempted,
                    "note": note,
                },
            )

        return ResolvedMedia(
            text=f"[Documento — resumo] {final_summary}",
            media_type="document",
            raw_text=final_summary,
            structured_payload={
                "media_type": "document",
                "mimetype": mimetype,
                "filename": filename,
                "size_bytes": len(doc_bytes),
                "extracted_chars": len(extracted_text),
                "rasterized": bool(rasterized_summary),
                "summary": final_summary,
            },
        )

    # ─── OpenAI calls ──────────────────────────────────────────────────
    async def _call_whisper(self, audio_bytes: bytes, *, filename: str) -> str:
        if not self._openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._openai_api_key)
        buffer = BytesIO(audio_bytes)
        buffer.name = filename
        response = await client.audio.transcriptions.create(
            model=self._audio_model,
            file=buffer,
            language="pt",
        )
        return (getattr(response, "text", "") or "").strip()

    async def _call_vision(
        self, image_bytes: bytes, *, mimetype: str, prompt: str
    ) -> str:
        if not self._openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._openai_api_key)
        data_url = f"data:{mimetype};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        response = await client.chat.completions.create(
            model=self._vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        )
        return (response.choices[0].message.content or "").strip()

    async def _call_vision_multi(
        self,
        frames: list[bytes],
        *,
        prompt: str,
        mimetype: str = "image/jpeg",
    ) -> str:
        """Send multiple images in ONE chat completion so the model can
        reason about them as a sequence (video keyframes, before/after,
        multi-page scans). Caps at 6 images to stay under token budget."""
        if not self._openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._openai_api_key)
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for frame in frames[:6]:
            data_url = f"data:{mimetype};base64,{base64.b64encode(frame).decode('ascii')}"
            content.append({"type": "image_url", "image_url": {"url": data_url}})
        response = await client.chat.completions.create(
            model=self._vision_model,
            messages=[{"role": "user", "content": content}],
        )
        return (response.choices[0].message.content or "").strip()

    async def _summarize_document_text(self, text: str) -> str:
        if not self._openai_api_key or not text.strip():
            return ""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._openai_api_key)
        snippet = text[:12000]
        response = await client.chat.completions.create(
            model=self._vision_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Resuma o texto a seguir em pt-BR no formato:\n"
                        "Tipo: <tipo do documento>\n"
                        "Resumo: <2 a 4 frases>\n"
                        "Dados visiveis:\n- <campo>: <valor>\n...\n\n"
                        "NUNCA diga que nao consegue resumir — descreva o "
                        "que voce LE no texto. Liste os campos mais "
                        "relevantes (nome, valores, datas, codigos, "
                        "enderecos, partes envolvidas, etc.). Transcreva "
                        "textos curtos como aparecem; nao invente."
                    ),
                },
                {"role": "user", "content": snippet},
            ],
        )
        return (response.choices[0].message.content or "").strip()

    # ─── Network ───────────────────────────────────────────────────────
    async def _download(self, url: str) -> bytes:
        """Download media bytes from WAHA.

        WAHA emits media URLs using its OWN external-facing host (e.g.
        ``http://localhost:3000/api/files/...`` because WAHA's web UI
        runs on the operator's laptop). From inside the app container,
        ``localhost`` is the app itself — the URL must be rewritten to
        the Docker-internal WAHA hostname before the GET. The X-Api-Key
        is forwarded so WAHA's media endpoint accepts the request.
        """
        resolved_url = self._rewrite_waha_url(url)
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            response = await client.get(resolved_url, headers=self._waha_headers())
            response.raise_for_status()
            return response.content

    def _rewrite_waha_url(self, url: str) -> str:
        """Map an externally-emitted WAHA URL onto our internal base.

        Recognises any WAHA file/media path; swaps the scheme + host +
        port from whatever WAHA reported (typically ``localhost:3000``
        or the operator's machine name) onto ``self._waha_base_url``.
        Non-WAHA URLs (e.g. raw WhatsApp CDN) pass through untouched.
        """
        if not url or not self._waha_base_url:
            return url
        try:
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(url)
            # Heuristic: WAHA media paths start with /api/files/ or
            # /api/{session}/files/. Anything else is left alone (e.g.
            # WhatsApp CDN URLs that don't need our key).
            if not parsed.path.startswith("/api/"):
                return url
            base = urlparse(self._waha_base_url)
            rewritten = parsed._replace(
                scheme=base.scheme or parsed.scheme,
                netloc=base.netloc or parsed.netloc,
            )
            return urlunparse(rewritten)
        except Exception:
            return url

    def _waha_headers(self) -> dict[str, str]:
        return {"X-Api-Key": self._waha_api_key} if self._waha_api_key else {}


# ─── Helpers ───────────────────────────────────────────────────────────
def _looks_like_refusal(text: str) -> bool:
    """Detect vision-model refusals that defeat the document pipeline.

    Common shapes: 'não foi possível extrair', 'não consegui ler',
    'sem texto', 'desculpe', plus very short replies under 40 chars
    (real summaries are always longer). When this fires, the document
    resolver retries vision with a more forceful directive.
    """
    if not text:
        return True
    lower = text.lower().strip()
    if len(lower) < 40:
        return True
    refusal_markers = (
        "não foi possível",
        "nao foi possivel",
        "não consegui",
        "nao consegui",
        "sem texto",
        "documento ilegível",
        "documento ilegivel",
        "desculpe",
        "i'm sorry",
        "i cannot",
        "unable to",
    )
    return any(marker in lower for marker in refusal_markers)


def _filename_for_mimetype(mimetype: str, default: str = "audio.ogg") -> str:
    mt = (mimetype or "").lower()
    if "ogg" in mt or "opus" in mt:
        return "audio.ogg"
    if "mp3" in mt or "mpeg" in mt:
        return "audio.mp3"
    if "wav" in mt:
        return "audio.wav"
    if "m4a" in mt or "mp4" in mt or "aac" in mt:
        return "audio.m4a"
    if "webm" in mt:
        return "audio.webm"
    return default


def _ext_for(mimetype: str, default: str) -> str:
    guess = mimetypes.guess_extension(mimetype or "") if mimetype else None
    return guess or default


def _looks_like_document(mimetype: str, filename: str | None) -> bool:
    if not filename and not mimetype:
        return False
    DOC_TYPES = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/plain",
        "text/csv",
    }
    if mimetype and mimetype.lower() in DOC_TYPES:
        return True
    if filename:
        lower = filename.lower()
        return any(lower.endswith(ext) for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".csv"))
    return False


def _extract_keyframes_via_ffmpeg(
    video_bytes: bytes,
    *,
    input_ext: str = ".mp4",
    count: int = 4,
    max_width: int = 768,
) -> list[bytes]:
    """Sample N evenly-spaced JPEG frames from a video.

    Strategy: probe the duration via ``ffprobe``, divide into N+1
    intervals, grab the middle frame of each interval, scale to
    ``max_width`` px to keep the vision payload small. Returns an
    empty list when ffmpeg/ffprobe are unavailable or the video is
    unreadable — callers compose around the empty list.

    Frame count default 4 is a compromise: 1-2 frames miss action;
    8+ inflates the chat-completion token bill without adding much.
    """
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return []
    with tempfile.TemporaryDirectory() as workdir:
        src = Path(workdir) / f"video{input_ext}"
        src.write_bytes(video_bytes)

        # Duration probe.
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(src),
                ],
                capture_output=True,
                check=True,
                timeout=20,
                text=True,
            )
            duration = float((probe.stdout or "0").strip() or 0)
        except Exception:
            duration = 0.0
        if duration <= 0:
            return []

        # Pick N evenly-spaced timestamps, biased to the interior of
        # the video (skipping the first/last 10%).
        interior_start = duration * 0.1
        interior_end = duration * 0.9
        if interior_end <= interior_start:
            interior_start, interior_end = 0.0, duration
        if count <= 1:
            timestamps = [interior_start + (interior_end - interior_start) / 2]
        else:
            step = (interior_end - interior_start) / (count - 1)
            timestamps = [interior_start + i * step for i in range(count)]

        frames: list[bytes] = []
        for idx, ts in enumerate(timestamps):
            out = Path(workdir) / f"frame-{idx:02d}.jpg"
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-ss",
                        f"{ts:.3f}",
                        "-i",
                        str(src),
                        "-frames:v",
                        "1",
                        "-vf",
                        f"scale='min({max_width},iw)':-2",
                        "-q:v",
                        "4",
                        str(out),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
            except Exception:
                continue
            if out.exists() and out.stat().st_size > 0:
                frames.append(out.read_bytes())
        return frames


def _extract_audio_via_ffmpeg(video_bytes: bytes, *, input_ext: str = ".mp4") -> bytes | None:
    """Use ffmpeg (already in the backend image for the upload pipeline)
    to extract a compressed audio track suitable for Whisper. Returns
    None if ffmpeg is unavailable or fails."""
    if not shutil.which("ffmpeg"):
        return None
    with tempfile.TemporaryDirectory() as workdir:
        src = Path(workdir) / f"video{input_ext}"
        dst = Path(workdir) / "audio.ogg"
        src.write_bytes(video_bytes)
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(src),
                    "-vn",
                    "-acodec",
                    "libopus",
                    "-b:a",
                    "32k",
                    str(dst),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
        except Exception:
            return None
        if not dst.exists() or dst.stat().st_size == 0:
            return None
        return dst.read_bytes()


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF using PyMuPDF's text layer.

    Mirrors the noc ERP pattern in
    ``erp-imobiliario/.../certidoes_service.py``: open with ``fitz``,
    iterate pages, accumulate ``page.get_text()``. PyMuPDF is faster
    than pdfminer.six for the text-layer-extract case and we already
    depend on it for the rasterize fallback.

    Falls back to pdfminer.six when fitz is unavailable (defensive —
    both are in requirements.txt). Returns empty string on failure;
    callers fall through to rasterize + vision.
    """
    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError:
        logger.info("PyMuPDF not installed; trying pdfminer.six")
        try:
            from pdfminer.high_level import extract_text  # type: ignore

            return extract_text(BytesIO(pdf_bytes)) or ""
        except ImportError:
            logger.info("pdfminer.six not installed either; text extraction skipped")
            return ""
        except Exception:
            logger.exception("pdfminer extraction failed")
            return ""

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        logger.exception("fitz: failed to open document")
        return ""
    parts: list[str] = []
    try:
        for page in doc:
            try:
                text = page.get_text().strip()
                if text:
                    parts.append(text)
            except Exception:
                logger.exception("fitz: page text extraction failed")
                continue
    finally:
        try:
            doc.close()
        except Exception:
            pass
    extracted = "\n\n".join(parts)
    logger.info(
        "PDF text extraction: %d pages with text, %d chars total",
        len(parts),
        len(extracted),
    )
    return extracted


def _rasterize_pdf_pages(
    pdf_bytes: bytes,
    *,
    max_pages: int = 3,
    max_width: int = 1024,
) -> list[bytes]:
    """Render the first ``max_pages`` of a PDF as JPEG bytes.

    Uses PyMuPDF (``fitz``) when installed. Returns an empty list when
    PyMuPDF is missing OR the PDF can't be opened — callers compose
    around the empty list. JPEGs are scaled so the widest dimension is
    ``max_width`` to keep the vision payload reasonable.
    """
    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError:
        logger.info("PyMuPDF not installed; PDF rasterization skipped")
        return []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        logger.exception("PyMuPDF: failed to open document")
        return []
    images: list[bytes] = []
    try:
        for page_index in range(min(max_pages, doc.page_count)):
            page = doc.load_page(page_index)
            # Scale matrix so the rendered width approaches max_width.
            page_width = page.rect.width or 1
            zoom = max(1.0, min(3.0, max_width / page_width))
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            try:
                jpeg = pix.tobytes("jpeg")
            except Exception:
                # Old PyMuPDF builds: fall back to PNG.
                jpeg = pix.tobytes("png")
            images.append(jpeg)
    finally:
        try:
            doc.close()
        except Exception:
            pass
    return images


def make_media_service() -> MediaService:
    """Default factory using product settings — used by webhook + chat
    routers so they don't have to know the construction details."""
    return MediaService(
        waha_base_url=settings.waha_base_url,
        waha_api_key=settings.waha_api_key,
        openai_api_key=settings.openai_api_key,
        audio_model=getattr(settings, "openai_audio_model", "gpt-4o-mini-transcribe"),
        vision_model=getattr(settings, "openai_vision_model", settings.openai_chat_model),
    )


__all__ = ["MediaService", "ResolvedMedia", "make_media_service"]
