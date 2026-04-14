"""
Focus Sessions Router — Pomodoro / Deep Work / Free focus sessions for Daily Life.

CRUD for focus sessions with stats aggregation (total sessions, total minutes, by type).
"""
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_user_client
from noctusai_shared.responses import success_response, paginated_response, ok_response
from noctusai_shared.auth import first_or_none

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/foco", tags=["Focus Sessions"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FocusCreate(BaseModel):
    tipo: str = Field(default="pomodoro", pattern="^(pomodoro|deep_work|livre)$")
    duracao_minutos: int = Field(..., ge=1, le=480)
    tarefa_id: Optional[str] = None
    nota: Optional[str] = None


class FocusUpdate(BaseModel):
    fim: Optional[datetime] = None
    nota: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/stats")
async def stats_foco(authorization: Optional[str] = Header(None)):
    """Get focus session statistics for the current user."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = (
        db.table("sessoes_foco")
        .select("tipo,duracao_minutos")
        .eq("user_id", str(user.id))
        .execute()
    )
    sessions = result.data or []

    total_sessions = len(sessions)
    total_minutos = sum(s.get("duracao_minutos", 0) for s in sessions)
    by_tipo: dict[str, int] = {}
    for s in sessions:
        t = s.get("tipo", "livre")
        by_tipo[t] = by_tipo.get(t, 0) + 1

    return success_response({
        "total_sessoes": total_sessions,
        "total_minutos": total_minutos,
        "por_tipo": by_tipo,
    })


@router.get("")
async def listar_sessoes(
    authorization: Optional[str] = Header(None),
    tipo: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List focus sessions with optional type filter."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    query = db.table("sessoes_foco").select("*", count="exact").eq("user_id", str(user.id))

    if tipo:
        query = query.eq("tipo", tipo)

    query = query.order("inicio", desc=True)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return paginated_response(result.data or [], result.count or 0, page, page_size)


@router.post("")
async def criar_sessao(body: FocusCreate, authorization: Optional[str] = Header(None)):
    """Start a new focus session."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("sessoes_foco").insert({
        "user_id": str(user.id),
        "tipo": body.tipo,
        "duracao_minutos": body.duracao_minutos,
        "tarefa_id": body.tarefa_id,
        "nota": body.nota,
        "inicio": datetime.utcnow().isoformat(),
    }).execute()

    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar sessao de foco")

    return success_response(row)


@router.patch("/{session_id}")
async def atualizar_sessao(session_id: str, body: FocusUpdate, authorization: Optional[str] = Header(None)):
    """Update a focus session (complete, add notes)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    if "fim" in updates and updates["fim"]:
        updates["fim"] = updates["fim"].isoformat()

    result = (
        db.table("sessoes_foco")
        .update(updates)
        .eq("id", session_id)
        .eq("user_id", str(user.id))
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada")

    return success_response(row)


@router.delete("/{session_id}")
async def deletar_sessao(session_id: str, authorization: Optional[str] = Header(None)):
    """Delete a focus session."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = (
        db.table("sessoes_foco")
        .delete()
        .eq("id", session_id)
        .eq("user_id", str(user.id))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada")

    return ok_response("Sessao de foco removida")
