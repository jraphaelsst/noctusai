"""
Schedule Router — Calendar events and appointments for Daily Life.

Manages events with categories, recurrence, reminders, and location support.
"""
import logging
from typing import Optional
from datetime import date, datetime

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_org_id, get_user_client
from app.services.schedule_service import expandir_recorrencias
from noctusai_lib.responses import success_response, paginated_response, ok_response
from noctusai_lib.auth import first_or_none

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/schedule", tags=["Schedule"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class EventCreate(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=300)
    descricao: Optional[str] = None
    categoria: Optional[str] = None
    data_inicio: datetime
    data_fim: Optional[datetime] = None
    dia_inteiro: bool = False
    local: Optional[str] = None
    lembrete_minutos: Optional[int] = None
    cor: Optional[str] = None
    recorrencia: Optional[str] = Field("nenhuma", pattern="^(nenhuma|diario|semanal|mensal|anual)$")
    recorrencia_fim: Optional[date] = None


class EventUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=1, max_length=300)
    descricao: Optional[str] = None
    categoria: Optional[str] = None
    data_inicio: Optional[datetime] = None
    data_fim: Optional[datetime] = None
    dia_inteiro: Optional[bool] = None
    local: Optional[str] = None
    lembrete_minutos: Optional[int] = None
    cor: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(agendado|concluido|cancelado)$")
    recorrencia: Optional[str] = Field(None, pattern="^(nenhuma|diario|semanal|mensal|anual)$")
    recorrencia_fim: Optional[date] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def listar_eventos(
    authorization: Optional[str] = Header(None),
    data_inicio: Optional[str] = Query(None, description="ISO date filter start"),
    data_fim: Optional[str] = Query(None, description="ISO date filter end"),
    categoria: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List user calendar events with optional date range and category filters."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    query = db.table("eventos").select("*", count="exact").eq("user_id", str(user.id))

    if data_inicio:
        query = query.gte("data_inicio", data_inicio)
    if data_fim:
        query = query.lte("data_inicio", data_fim)
    if categoria:
        query = query.eq("categoria", categoria)

    query = query.order("data_inicio", desc=False)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return paginated_response(result.data or [], result.count or 0, page, page_size)


@router.post("")
async def criar_evento(body: EventCreate, authorization: Optional[str] = Header(None)):
    """Create a new calendar event."""
    user, token = await get_current_user(authorization)
    org_id = get_org_id(user)
    db = get_user_client(token)

    result = db.table("eventos").insert({
        "user_id": str(user.id),
        "org_id": org_id,
        "titulo": body.titulo,
        "descricao": body.descricao,
        "categoria": body.categoria,
        "data_inicio": body.data_inicio.isoformat(),
        "data_fim": body.data_fim.isoformat() if body.data_fim else None,
        "dia_inteiro": body.dia_inteiro,
        "local": body.local,
        "lembrete_minutos": body.lembrete_minutos,
        "cor": body.cor,
        "status": "agendado",
        "recorrencia": body.recorrencia or "nenhuma",
        "recorrencia_fim": str(body.recorrencia_fim) if body.recorrencia_fim else None,
    }).execute()

    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar evento")

    return success_response(row)


@router.get("/{event_id}")
async def obter_evento(event_id: str, authorization: Optional[str] = Header(None)):
    """Get a single event by ID."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("eventos").select("*").eq("id", event_id).eq("user_id", str(user.id)).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Evento nao encontrado")

    return success_response(row)


@router.patch("/{event_id}")
async def atualizar_evento(event_id: str, body: EventUpdate, authorization: Optional[str] = Header(None)):
    """Update an existing event."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    if "data_inicio" in updates:
        updates["data_inicio"] = updates["data_inicio"].isoformat()
    if "data_fim" in updates:
        updates["data_fim"] = updates["data_fim"].isoformat()
    if "recorrencia_fim" in updates and updates["recorrencia_fim"]:
        updates["recorrencia_fim"] = str(updates["recorrencia_fim"])

    result = (
        db.table("eventos")
        .update(updates)
        .eq("id", event_id)
        .eq("user_id", str(user.id))
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Evento nao encontrado")

    return success_response(row)


@router.delete("/{event_id}")
async def deletar_evento(event_id: str, authorization: Optional[str] = Header(None)):
    """Delete a calendar event."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("eventos").delete().eq("id", event_id).eq("user_id", str(user.id)).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Evento nao encontrado")

    return ok_response("Evento removido")
