"""
Goals & Habits Router — Goal tracking and habit management for Daily Life.

Supports goals with targets and deadlines, plus recurring habits with
daily/weekly/monthly tracking.
"""
import logging
from typing import Optional
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from app.dependencies import get_user_client, get_current_user_org
from app.services.goals_service import register_checkin
from noctusai_lib.primitives.responses import success_response, paginated_response, ok_response
from noctusai_lib.api.auth import first_or_none
from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/goals", tags=["Goals & Habits"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GoalCreate(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=300)
    descricao: Optional[str] = None
    tipo: str = Field(default="meta", pattern="^(meta|habito)$")
    categoria: Optional[str] = None
    meta_valor: Optional[float] = None
    unidade: Optional[str] = None
    frequencia: Optional[str] = Field(None, pattern="^(diario|semanal|mensal)$")
    data_limite: Optional[date] = None


class GoalUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=1, max_length=300)
    descricao: Optional[str] = None
    categoria: Optional[str] = None
    meta_valor: Optional[float] = None
    valor_atual: Optional[float] = None
    unidade: Optional[str] = None
    frequencia: Optional[str] = Field(None, pattern="^(diario|semanal|mensal)$")
    data_limite: Optional[date] = None
    status: Optional[str] = Field(None, pattern="^(ativa|concluida|pausada|cancelada)$")


class HabitCheckIn(BaseModel):
    data: date
    valor: Optional[float] = 1.0
    nota: Optional[str] = None


# ---------------------------------------------------------------------------
# Goal Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def listar_metas(
    auth: tuple = Depends(get_current_user_org),
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List user goals/habits with optional filters."""
    user, token, _org_id = auth
    db = get_user_client(token)

    query = db.table("metas").select("*", count="exact").eq("user_id", str(user.id))

    if tipo:
        query = query.eq("tipo", tipo)
    if status:
        query = query.eq("status", status)

    query = query.order("created_at", desc=True)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return paginated_response(result.data or [], result.count or 0, page, page_size)


@router.post("")
async def criar_meta(body: GoalCreate, auth: tuple = Depends(get_current_user_org)):
    """Create a new goal or habit."""
    user, token, org_id = auth
    db = get_user_client(token)

    result = db.table("metas").insert({
        "user_id": str(user.id),
        "org_id": org_id,
        "titulo": body.titulo,
        "descricao": body.descricao,
        "tipo": body.tipo,
        "categoria": body.categoria,
        "meta_valor": body.meta_valor,
        "valor_atual": 0,
        "unidade": body.unidade,
        "frequencia": body.frequencia,
        "data_limite": str(body.data_limite) if body.data_limite else None,
        "status": "ativa",
    }).execute()

    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar meta")

    return success_response(row)


@router.get("/{goal_id}")
async def obter_meta(goal_id: str, auth: tuple = Depends(get_current_user_org)):
    """Get a single goal or habit by ID."""
    user, token, _org_id = auth
    db = get_user_client(token)

    result = (
        db.table("metas")
        .select("*")
        .eq("id", goal_id)
        .eq("user_id", str(user.id))
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Meta nao encontrada")

    return success_response(result.data)


@router.patch("/{goal_id}")
async def atualizar_meta(goal_id: str, body: GoalUpdate, auth: tuple = Depends(get_current_user_org)):
    """Update an existing goal or habit."""
    user, token, _org_id = auth
    db = get_user_client(token)

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    if "data_limite" in updates and updates["data_limite"]:
        updates["data_limite"] = str(updates["data_limite"])

    result = (
        db.table("metas")
        .update(updates)
        .eq("id", goal_id)
        .eq("user_id", str(user.id))
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Meta nao encontrada")

    return success_response(row)


@router.delete("/{goal_id}")
async def deletar_meta(goal_id: str, auth: tuple = Depends(get_current_user_org)):
    """Delete a goal or habit."""
    user, token, _org_id = auth
    db = get_user_client(token)

    delete_or_404(db, "metas", ("id", goal_id), ("user_id", str(user.id)), message="Meta nao encontrada")

    return ok_response("Meta removida")


# ---------------------------------------------------------------------------
# Habit Check-In Endpoints
# ---------------------------------------------------------------------------

@router.post("/{goal_id}/checkin")
async def registrar_checkin(goal_id: str, body: HabitCheckIn, auth: tuple = Depends(get_current_user_org)):
    """Register a daily check-in for a habit."""
    user, token, _org_id = auth
    db = get_user_client(token)

    row = register_checkin(
        db=db,
        goal_id=goal_id,
        user_id=str(user.id),
        data=str(body.data),
        valor=body.valor,
        nota=body.nota,
    )

    return success_response(row)


@router.get("/{goal_id}/checkins")
async def listar_checkins(
    goal_id: str,
    auth: tuple = Depends(get_current_user_org),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    """List check-ins for a specific goal/habit."""
    user, token, _org_id = auth
    db = get_user_client(token)

    query = (
        db.table("checkins")
        .select("*", count="exact")
        .eq("meta_id", goal_id)
        .eq("user_id", str(user.id))
        .order("data", desc=True)
    )

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return paginated_response(result.data or [], result.count or 0, page, page_size)
