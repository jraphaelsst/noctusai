"""
Notifications Router — In-app notification management.

GET   /api/notifications              — List notifications for current user (paginated, newest first)
GET   /api/notifications/unread-count — Get unread notification count
PATCH /api/notifications/{id}/read    — Mark a single notification as read
PATCH /api/notifications/read-all     — Mark all notifications as read
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query

from app.database import get_admin_client
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("")
async def listar_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    authorization: Optional[str] = Header(None),
):
    """List notifications for the current user (paginated, newest first)."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    offset = (page - 1) * page_size

    # Get total count
    count_result = db.table("notifications").select(
        "id", count="exact"
    ).eq("user_id", user.id).execute()
    total = count_result.count if count_result.count is not None else len(count_result.data or [])

    # Get paginated results
    result = db.table("notifications").select("*").eq(
        "user_id", user.id
    ).order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

    return {
        "data": result.data or [],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/unread-count")
async def get_unread_count(authorization: Optional[str] = Header(None)):
    """Get the unread notification count for the current user."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    result = db.table("notifications").select(
        "id", count="exact"
    ).eq("user_id", user.id).eq("read", False).execute()

    count = result.count if result.count is not None else len(result.data or [])
    return {"unread_count": count}


@router.patch("/read-all")
async def marcar_todas_lidas(authorization: Optional[str] = Header(None)):
    """Mark all notifications as read for the current user."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    result = db.table("notifications").update(
        {"read": True}
    ).eq("user_id", user.id).eq("read", False).execute()

    updated = len(result.data) if result.data else 0
    logger.info(f"Marked all notifications as read: user={user.id} count={updated}")
    return {"data": {"updated": updated}}


@router.patch("/{notification_id}/read")
async def marcar_lida(notification_id: str, authorization: Optional[str] = Header(None)):
    """Mark a single notification as read."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    result = db.table("notifications").update(
        {"read": True}
    ).eq("id", notification_id).eq("user_id", user.id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")

    return {"data": result.data[0]}
