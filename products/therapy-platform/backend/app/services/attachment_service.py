"""
Attachment Service — file upload and AI processing for message attachments.

Supports images (OpenAI Vision) and audio (OpenAI Whisper) with graceful
degradation when OpenAI API key is not configured.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_AUDIO_TYPES = {"audio/mpeg", "audio/mp4", "audio/wav", "audio/ogg", "audio/webm"}
ALLOWED_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_AUDIO_TYPES
STORAGE_BUCKET = "therapy-messages"


async def upload_attachment(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    conversation_id: str,
    db: Any,
) -> Dict:
    """Upload a file attachment to Supabase Storage.

    Validates file size (max 50MB) and type (image/* or audio/*).
    Returns the public URL, file type, and file size.
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
    import uuid
    file_ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    storage_path = f"{conversation_id}/{uuid.uuid4().hex}.{file_ext}"

    try:
        bucket = db.storage.from_(STORAGE_BUCKET)
        bucket.upload(storage_path, file_bytes, {"content-type": content_type})
        public_url_response = bucket.get_public_url(storage_path)
        file_url = public_url_response if isinstance(public_url_response, str) else str(public_url_response)
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
        "file_type": file_type,
        "file_size": file_size,
    }


async def process_attachment_with_ai(
    file_url: str,
    file_type: str,
    db: Any,
) -> Optional[str]:
    """Process an attachment with OpenAI.

    For images: uses Vision API for description.
    For audio: uses Whisper for transcription.
    Returns AI-processed content or None on failure/missing key.
    """
    if not settings.openai_api_key:
        logger.info("OpenAI API key not configured — skipping AI attachment processing")
        return None

    try:
        import openai
        client = openai.OpenAI(api_key=settings.openai_api_key)

        if file_type == "image":
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Descreva esta imagem de forma concisa em português. "
                                    "Se parecer ser um documento clínico ou anotação, "
                                    "extraia o conteúdo textual principal."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": file_url},
                            },
                        ],
                    }
                ],
                max_tokens=500,
            )
            return response.choices[0].message.content

        elif file_type == "audio":
            # Download the file for Whisper
            import httpx
            async with httpx.AsyncClient() as http:
                audio_resp = await http.get(file_url)
                if audio_resp.status_code != 200:
                    logger.warning("Failed to download audio for transcription: %s", file_url)
                    return None

            import tempfile
            import os
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp.write(audio_resp.content)
                tmp_path = tmp.name

            try:
                with open(tmp_path, "rb") as audio_file:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="pt",
                    )
                return transcript.text
            finally:
                os.unlink(tmp_path)

    except Exception as e:
        logger.error("AI attachment processing failed: %s", e)
        return None
