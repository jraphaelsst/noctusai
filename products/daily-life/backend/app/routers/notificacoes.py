"""
Notification endpoints — proxies to the core platform's public.notifications table.

Notifications are a platform-level feature shared across all NoctusAI products.
The actual data lives in `public.notifications` (core schema).
This router provides a Portuguese-language API that maps to the core table columns.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import get_current_user
from app.database import get_core_client
from noctusai_shared.responses import success_response, paginated_response, ok_response
from noctusai_shared.auth import first_or_none
from noctusai_shared.notifications import map_notification_to_pt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notificacoes", tags=["notificacoes"])


@router.get("")
async def listar_notificacoes(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    apenas_nao_lidas: bool = Query(False),
):
    """List user notifications (unread first)."""
    user, _ = await get_current_user(authorization)
    db = get_core_client()

    query = db.table("notifications").select("*", count="exact").eq("user_id", user.id)
    if apenas_nao_lidas:
        query = query.eq("read", False)
    query = query.order("created_at", desc=True)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    mapped = [map_notification_to_pt(r) for r in (result.data or [])]
    return paginated_response(mapped, result.count or 0, page, page_size)


@router.get("/contagem")
async def contagem_nao_lidas(authorization: Optional[str] = Header(None)):
    """Get count of unread notifications."""
    user, _ = await get_current_user(authorization)
    db = get_core_client()

    result = (
        db.table("notifications")
        .select("id", count="exact")
        .eq("user_id", user.id)
        .eq("read", False)
        .execute()
    )

    return success_response({"nao_lidas": result.count or 0})


@router.patch("/{notificacao_id}/ler")
async def marcar_como_lida(notificacao_id: str, authorization: Optional[str] = Header(None)):
    """Mark a single notification as read."""
    user, _ = await get_current_user(authorization)
    db = get_core_client()

    result = (
        db.table("notifications")
        .update({"read": True})
        .eq("id", notificacao_id)
        .eq("user_id", user.id)
        .execute()
    )
    row = first_or_none(result)

    if not row:
        raise HTTPException(status_code=404, detail="Notificacao nao encontrada")

    return success_response(map_notification_to_pt(row))


@router.post("/ler-todas")
async def marcar_todas_como_lidas(authorization: Optional[str] = Header(None)):
    """Mark all notifications as read."""
    user, _ = await get_current_user(authorization)
    db = get_core_client()

    result = (
        db.table("notifications")
        .update({"read": True})
        .eq("user_id", user.id)
        .eq("read", False)
        .execute()
    )

    count = len(result.data) if result.data else 0
    return ok_response(f"{count} notificacoes marcadas como lidas")
