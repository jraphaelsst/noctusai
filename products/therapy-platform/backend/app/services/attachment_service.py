"""Attachment Service — file upload + AI processing for message attachments.

**2026-04-22 hardening** (compliance-audit-reconciliation Phase 4 per Q4):

- Uploads go to a PRIVATE bucket. Upload returns a **short-lived signed URL**
  (5-minute expiry) instead of a public URL. Persistent access requires
  regenerating a fresh signed URL server-side via `generate_signed_url()` —
  the authoritative reference is `storage_path`, not the URL.
- AI processing is **server-mediated** — bytes are passed directly to the
  LLM client (Vision / Whisper) instead of a URL. OpenAI never sees a
  URL that could be persisted or re-used.
- **Ops requirement** (out-of-band, NOT automated by this service): the
  `therapy-messages` bucket MUST be created as PRIVATE in Supabase. As of
  2026-04-22 the bucket does not yet exist in the live project; it will be
  created when the attachment feature is enabled. Creating it as PUBLIC
  would defeat the signed-URL protection (direct access works without a
  signed URL on public buckets).

**LGPD**: Patient-uploaded files may contain clinical documents or raw voice
— Art. 11 sensitive data. Signed URLs limit exposure window; server-mediated
AI processing eliminates URL persistence at third parties. Responses not
cached (audio / vision skip the response-cache layer).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_AUDIO_TYPES = {"audio/mpeg", "audio/mp4", "audio/wav", "audio/ogg", "audio/webm"}
ALLOWED_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_AUDIO_TYPES
STORAGE_BUCKET = "therapy-messages"
SIGNED_URL_TTL_SECONDS = 300  # 5 minutes — caller must regenerate for persistent access


def _extract_signed_url(signed_url_response: Any) -> str:
    """Supabase-py `create_signed_url` returns either a dict `{signedURL: ...}`
    or a raw string depending on SDK version. Normalize to the string."""
    if isinstance(signed_url_response, dict):
        return signed_url_response.get("signedURL") or signed_url_response.get("signed_url") or ""
    if isinstance(signed_url_response, str):
        return signed_url_response
    return str(signed_url_response)


async def upload_attachment(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    conversation_id: str,
    db: Any,
) -> Dict:
    """Upload a file to Supabase Storage + return a short-lived signed URL.

    Validates file size (max 50MB) and type (image/* or audio/*). The caller
    receives `url` (signed, 5-min expiry), `storage_path` (authoritative
    reference — use with `generate_signed_url` to get a fresh URL later),
    `file_type`, and `file_size`.
    """
    # Validate file size
    file_size = len(file_bytes)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=422,
            detail=f"Arquivo excede o limite de 50MB. Tamanho: {file_size / (1024 * 1024):.1f}MB",
        )

    # Validate content type
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo de arquivo não suportado: {content_type}. Aceitos: imagens e áudios",
        )

    # Upload to Supabase Storage
    file_ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    storage_path = f"{conversation_id}/{uuid.uuid4().hex}.{file_ext}"

    try:
        bucket = db.storage.from_(STORAGE_BUCKET)
        bucket.upload(storage_path, file_bytes, {"content-type": content_type})
        signed_response = bucket.create_signed_url(storage_path, SIGNED_URL_TTL_SECONDS)
        file_url = _extract_signed_url(signed_response)
    except Exception as e:
        logger.error("Failed to upload attachment: %s", e)
        raise HTTPException(status_code=500, detail="Erro ao fazer upload do arquivo")

    # Determine file category
    file_type = "image" if content_type in ALLOWED_IMAGE_TYPES else "audio"

    logger.info(
        "Attachment uploaded: conv=%s type=%s size=%d path=%s",
        conversation_id, file_type, file_size, storage_path,
    )

    return {
        "url": file_url,
        "storage_path": storage_path,
        "file_type": file_type,
        "file_size": file_size,
        "expires_in": SIGNED_URL_TTL_SECONDS,
    }


async def generate_signed_url(
    storage_path: str,
    db: Any,
    expires_in: int = SIGNED_URL_TTL_SECONDS,
) -> str:
    """Generate a fresh signed URL for an existing `storage_path`.

    Caller is responsible for authorization (verifying the requesting user
    has access to the conversation that owns this attachment). This
    function trusts the caller's auth check.
    """
    try:
        bucket = db.storage.from_(STORAGE_BUCKET)
        signed_response = bucket.create_signed_url(storage_path, expires_in)
        return _extract_signed_url(signed_response)
    except Exception as e:
        logger.error("Failed to generate signed URL for %s: %s", storage_path, e)
        raise HTTPException(status_code=500, detail="Erro ao gerar URL assinada")


async def process_attachment_with_ai(
    file_bytes: bytes,
    file_type: str,
    clinic_id: Optional[str] = None,
) -> Optional[str]:
    """Process a patient-uploaded attachment via the shared LLM client.

    **Server-mediated**: `file_bytes` is passed directly to the LLM client
    (no URL fetch, no third-party URL leakage). For images, the provider
    receives the bytes as a base64-encoded data URL — never a persistent
    reference. For audio, Whisper already accepts bytes natively.

    For images: uses Vision (default: GPT-4o) to describe / extract text.
    For audio: uses Whisper for transcription.
    Returns AI-processed content or None on failure / missing key.

    `clinic_id` threads through as `org_id` so the clinic's Tier 1 provider
    key is used when configured.

    **LGPD**: Art. 11 sensitive data. Vision + Whisper responses are not
    cached. See `LGPD-WARNINGS.md` entry `patient-attachment-to-llm`.
    """
    from noctusai_lib.integrations.llm import LLMNotConfigured, analyze_image, transcribe_audio

    try:
        if file_type == "image":
            return await analyze_image(
                image=file_bytes,  # server-mediated: bytes → base64 data URL by provider
                prompt=(
                    "Descreva esta imagem de forma concisa em português. "
                    "Se parecer ser um documento clínico ou anotação, "
                    "extraia o conteúdo textual principal."
                ),
                model="gpt-4o",
                max_tokens=500,
                org_id=clinic_id,
            )

        elif file_type == "audio":
            return await transcribe_audio(
                file_bytes,
                model="whisper-1",
                filename="attachment.mp3",
                language="pt",
                org_id=clinic_id,
            )

    except LLMNotConfigured:
        logger.info("LLM not configured — skipping AI attachment processing")
        return None
    except Exception as e:
        logger.error("AI attachment processing failed: %s", e)
        return None
