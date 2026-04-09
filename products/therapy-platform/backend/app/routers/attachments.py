"""
Attachments Router — file upload for message attachments.

Prefix: /api/attachments
Supports images and audio files up to 50MB with optional AI processing.
"""
import logging
from typing import Optional

from fastapi import APIRouter, File, Header, UploadFile, Form

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

    Returns the file URL and optional AI-processed content (image description
    or audio transcription).
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

    # Attempt AI processing (graceful degradation)
    ai_content = await attachment_service.process_attachment_with_ai(
        file_url=result["url"],
        file_type=result["file_type"],
        db=db,
    )
    result["ai_processed_content"] = ai_content

    return success_response(result)
