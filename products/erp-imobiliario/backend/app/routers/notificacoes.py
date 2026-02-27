"""
Notification endpoints — manages user notifications and preferences.

Tables:
  erp.notificacoes — per-user notification records
  erp.notificacao_preferencias — notification channel preferences
"""
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_user_client
from app.exceptions import AppException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notificacoes", tags=["notificacoes"])


# ── Schemas ──────────────────────────────────────────────────────────

class PreferenciaUpdate(BaseModel):
    canal: Literal["app", "email", "whatsapp"]
    tipo_evento: str = Field(..., min_length=1, max_length=100)
    ativo: bool


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("")
async def listar_notificacoes(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    apenas_nao_lidas: bool = Query(False),
):
    """List user notifications (unread first)."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)

    query = sb.table("notificacoes").select("*", count="exact").eq("user_id", user.id)
    if apenas_nao_lidas:
        query = query.eq("is_read", False)
    query = query.order("created_at", desc=True)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return {
        "status": "success",
        "data": result.data or [],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": result.count or 0,
        },
    }


@router.get("/contagem")
async def contagem_nao_lidas(authorization: Optional[str] = Header(None)):
    """Get count of unread notifications."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)

    result = (
        sb.table("notificacoes")
        .select("id", count="exact")
        .eq("user_id", user.id)
        .eq("is_read", False)
        .execute()
    )

    return {"status": "success", "data": {"nao_lidas": result.count or 0}}


@router.patch("/{notificacao_id}/ler")
async def marcar_como_lida(
    notificacao_id: str,
    authorization: Optional[str] = Header(None),
):
    """Mark a single notification as read."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)

    result = (
        sb.table("notificacoes")
        .update({"is_read": True})
        .eq("id", notificacao_id)
        .eq("user_id", user.id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")

    return {"status": "success", "data": result.data[0]}


@router.post("/ler-todas")
async def marcar_todas_como_lidas(authorization: Optional[str] = Header(None)):
    """Mark all notifications as read."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)

    result = (
        sb.table("notificacoes")
        .update({"is_read": True})
        .eq("user_id", user.id)
        .eq("is_read", False)
        .execute()
    )

    count = len(result.data) if result.data else 0
    return {"status": "success", "message": f"{count} notificações marcadas como lidas"}


@router.get("/preferencias")
async def listar_preferencias(authorization: Optional[str] = Header(None)):
    """Get notification preferences for the current user."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)

    result = (
        sb.table("notificacao_preferencias")
        .select("*")
        .eq("user_id", user.id)
        .execute()
    )

    return {"status": "success", "data": result.data or []}


@router.patch("/preferencias")
async def atualizar_preferencia(
    body: PreferenciaUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update a notification preference (upsert)."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)
    org_id = user.user_metadata.get("org_id")

    data = {
        "org_id": org_id,
        "user_id": user.id,
        "canal": body.canal,
        "tipo_evento": body.tipo_evento,
        "ativo": body.ativo,
    }

    result = (
        sb.table("notificacao_preferencias")
        .upsert(data, on_conflict="user_id,canal,tipo_evento")
        .execute()
    )

    return {"status": "success", "data": result.data[0] if result.data else data}
