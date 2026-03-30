"""
Notification endpoints — proxies to the core platform's public.notifications table.

Notifications are a platform-level feature shared across all NoctusAI products.
The actual data lives in `public.notifications` (core schema), not in `erp`.
This router provides a Portuguese-language API that maps to the core table columns.

Preferences remain product-specific in `erp.notificacao_preferencias`.

Core table columns: id, user_id, org_id, type, title, message, metadata, read, created_at
ERP API fields:     id, user_id, org_id, tipo, titulo, mensagem, metadata, is_read, created_at
"""
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_user_client, get_org_id, first_or_none
from app.database import get_core_client
from app.responses import success_response, paginated_response, ok_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notificacoes", tags=["notificacoes"])


# ── Field Mapping (core English → ERP Portuguese) ────────────────────

def _map_to_pt(row: dict) -> dict:
    """Map core notification fields to Portuguese for the frontend."""
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "org_id": row.get("org_id"),
        "tipo": row.get("type"),
        "titulo": row.get("title"),
        "mensagem": row.get("message"),
        "metadata": row.get("metadata"),
        "is_read": row.get("read", False),
        "link": (row.get("metadata") or {}).get("link"),
        "created_at": row.get("created_at"),
    }


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
    user, _ = await get_current_user(authorization)
    db = get_core_client()

    query = db.table("notifications").select("*", count="exact").eq("user_id", user.id)
    if apenas_nao_lidas:
        query = query.eq("read", False)
    query = query.order("created_at", desc=True)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    mapped = [_map_to_pt(r) for r in (result.data or [])]
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
async def marcar_como_lida(
    notificacao_id: str,
    authorization: Optional[str] = Header(None),
):
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
        raise HTTPException(status_code=404, detail="Notificação não encontrada")

    return success_response(_map_to_pt(row))


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
    return ok_response(f"{count} notificações marcadas como lidas")


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

    return success_response(result.data or [])


@router.patch("/preferencias")
async def atualizar_preferencia(
    body: PreferenciaUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update a notification preference (upsert)."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)
    org_id = get_org_id(user)

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

    return success_response(result.data[0] if result.data else data)
