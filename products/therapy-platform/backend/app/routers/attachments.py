"""Attachments Router — file upload for message attachments.

Prefix: /api/attachments
Supports images and audio files up to 50MB with optional AI processing.

**2026-04-22 hardening** (compliance-audit-reconciliation Phase 4 per Q4):
- `POST /upload` returns a **5-min signed URL** + the authoritative
  `storage_path`. Callers store `storage_path` in their message records;
  re-fetch a fresh signed URL via `GET /signed-url` when needed.
- `GET /signed-url?storage_path=...` regenerates a signed URL after
  verifying the caller is a participant in the conversation that owns
  the attachment.
- AI processing now runs server-mediated on the bytes directly — no URL
  ever leaks to OpenAI.
"""
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile

from app.dependencies import get_current_user, get_user_client
from app.responses import success_response
from app.services import attachment_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/attachments", tags=["Attachments"])


@router.post("/upload")
async def upload_attachment(
    file: UploadFile = File(...),
    conversation_id: str = Form(...),
    authorization: Optional[str] = Header(None),
):
    """Upload a file attachment (images and audio, max 50MB).

    Returns the short-lived signed URL, authoritative storage_path, and
    optional AI-processed content (image description or audio transcription).
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    file_bytes = await file.read()
    content_type = file.content_type or "application/octet-stream"

    result = await attachment_service.upload_attachment(
        file_bytes=file_bytes,
        filename=file.filename or "upload",
        content_type=content_type,
        conversation_id=conversation_id,
        db=db,
    )

    # Server-mediated AI processing (graceful degradation) — bytes go
    # straight to the LLM client; no URL leaks to third parties.
    ai_content = await attachment_service.process_attachment_with_ai(
        file_bytes=file_bytes,
        file_type=result["file_type"],
    )
    result["ai_processed_content"] = ai_content

    return success_response(result)


@router.get("/signed-url")
async def get_signed_url(
    storage_path: str = Query(...),
    authorization: Optional[str] = Header(None),
):
    """Regenerate a fresh signed URL for an existing attachment.

    Verifies the caller is a participant in the conversation that owns the
    attachment. `storage_path` shape: `<conversation_id>/<uuid>.<ext>`.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # storage_path format: "<conversation_id>/<filename>"
    if "/" not in storage_path:
        raise HTTPException(status_code=400, detail="storage_path inválido")
    conversation_id = storage_path.split("/", 1)[0]

    # Authorization check: caller must be a participant in the conversation.
    # RLS on conversation_participants already scopes the query to the caller's
    # own memberships, so an empty result means "not a participant."
    membership = (
        db.table("conversation_participants")
        .select("conversation_id")
        .eq("conversation_id", conversation_id)
        .eq("participant_id", str(user.id))
        .execute()
    )
    if not (membership.data or []):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para acessar este anexo",
        )

    signed_url = await attachment_service.generate_signed_url(storage_path, db)
    return success_response({
        "url": signed_url,
        "storage_path": storage_path,
        "expires_in": attachment_service.SIGNED_URL_TTL_SECONDS,
    })
