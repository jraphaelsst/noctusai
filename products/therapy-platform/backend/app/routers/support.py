"""
Support Router — Platform admin support inbox.

Prefix: /api/support
Admin-only endpoints for managing support conversations.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.responses import paginated_response, success_response
from app.schemas.messaging import SendMessageRequest, ReportReviewRequest
from app.services import messaging_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/support", tags=["Support"])


def _require_admin(role: str):
    """Raise 403 if user is not a platform admin."""
    if role != "platform_admin":
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito a administradores da plataforma",
        )


@router.get("/conversations")
async def list_support_conversations(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all support conversations (admin only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    _require_admin(role)

    db = get_user_client(token)
    data, total = await messaging_service.list_support_conversations(
        page=page,
        page_size=page_size,
        db=db,
    )
    return paginated_response(data, total, page, page_size)


@router.get("/conversations/{conversation_id}/messages")
async def get_support_messages(
    conversation_id: str,
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """Get messages from a support conversation (admin only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    _require_admin(role)

    db = get_user_client(token)
    data, total = await messaging_service.get_messages(
        conversation_id=conversation_id,
        user_id=user.id,
        user_role=role,
        clinic_id=None,
        page=page,
        page_size=page_size,
        db=db,
    )
    return paginated_response(data, total, page, page_size)


@router.post("/conversations/{conversation_id}/messages")
async def send_support_message(
    conversation_id: str,
    body: SendMessageRequest,
    authorization: Optional[str] = Header(None),
):
    """Admin replies to a support conversation (sender_type=platform_support)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    _require_admin(role)

    db = get_user_client(token)
    msg = await messaging_service.send_message(
        conversation_id=conversation_id,
        sender_user_id=user.id,
        sender_type="platform_support",
        content=body.content,
        message_type=body.message_type,
        sender_clinic_id=None,
        db=db,
    )
    return success_response(msg)


@router.get("/reports")
async def list_reports(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all message reports (admin only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    _require_admin(role)

    db = get_user_client(token)
    query = (
        db.table("message_reports")
        .select("*", count="exact")
        .order("created_at", desc=True)
    )
    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return paginated_response(result.data or [], result.count or 0, page, page_size)


@router.patch("/reports/{report_id}")
async def review_report(
    report_id: str,
    body: ReportReviewRequest,
    authorization: Optional[str] = Header(None),
):
    """Admin reviews and resolves a message report."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    _require_admin(role)

    db = get_user_client(token)
    result = await messaging_service.review_report(
        report_id=report_id,
        admin_id=user.id,
        resolution=body.resolution,
        db=db,
    )
    return success_response(result)
