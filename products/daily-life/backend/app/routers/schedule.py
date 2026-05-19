"""
Schedule Router — Calendar events and appointments for Daily Life.

Manages events with categories, recurrence, reminders, and location support.
"""
import logging
from typing import Optional
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import Field

from app.dependencies import get_user_client, get_current_user_org
from app.services.schedule_service import expandir_recorrencias, RECURRING_VALUES
from noctusai_lib.primitives.responses import success_response, paginated_response, ok_response
from noctusai_lib.api.auth import first_or_none
from noctusai_lib.api.crud_safety import delete_or_404
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
def _as_date(value):
    """Parse an ISO date/datetime query string to a date.

    Returns None on absence/parse-failure (callers default the
    recurrence window). No silent except — a malformed filter is
    logged at DEBUG so it is observable, never swallowed.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, TypeError) as exc:
        logger.debug("schedule: unparseable date filter %r (%s)", value, exc)
        return None
router = APIRouter(prefix="/api/schedule", tags=["Schedule"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class EventCreate(StrictHttpModel):
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


class EventUpdate(StrictHttpModel):
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
    auth: tuple = Depends(get_current_user_org),
    data_inicio: Optional[str] = Query(None, description="ISO date filter start"),
    data_fim: Optional[str] = Query(None, description="ISO date filter end"),
    categoria: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List user calendar events with optional date range and category filters."""
    user, token, _org_id = auth
    db = get_user_client(token)

    query = db.table("eventos").select("*").eq("user_id", str(user.id))
    if data_fim:
        # Upper bound applies to all rows: a parent whose start is after
        # the window-end has no occurrences inside it (recurrence runs
        # forward from data_inicio).
        query = query.lte("data_inicio", data_fim)
    if data_inicio:
        # Q1 (schedule-recurrence-window-gap §2 — recurrence-aware lower
        # bound): a recurring parent that STARTED before the window can
        # still have occurrences inside it, so it must NOT be excluded by
        # the start lower-bound (expandir_recorrencias clips occurrences to
        # [inicio,fim]). Non-recurring rows keep the start-in-window
        # semantic unchanged (zero regression). recorrencia NULL/"nenhuma"
        # = non-recurring; the IN-list is the service vocabulary constant.
        query = query.or_(
            f"data_inicio.gte.{data_inicio},recorrencia.in.({','.join(RECURRING_VALUES)})"
        )
    if categoria:
        query = query.eq("categoria", categoria)

    query = query.order("data_inicio", desc=False)
    result = query.execute()
    _occurrences = expandir_recorrencias(
        result.data or [], _as_date(data_inicio), _as_date(data_fim)
    )
    _total = len(_occurrences)
    _offset = (page - 1) * page_size
    _page = _occurrences[_offset:_offset + page_size]
    return paginated_response(_page, _total, page, page_size)


@router.post("")
async def criar_evento(body: EventCreate, auth: tuple = Depends(get_current_user_org)):
    """Create a new calendar event."""
    user, token, org_id = auth
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
async def obter_evento(event_id: str, auth: tuple = Depends(get_current_user_org)):
    """Get a single event by ID."""
    user, token, _org_id = auth
    db = get_user_client(token)

    result = db.table("eventos").select("*").eq("id", event_id).eq("user_id", str(user.id)).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Evento nao encontrado")

    return success_response(row)


@router.patch("/{event_id}")
async def atualizar_evento(event_id: str, body: EventUpdate, auth: tuple = Depends(get_current_user_org)):
    """Update an existing event."""
    user, token, _org_id = auth
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
async def deletar_evento(event_id: str, auth: tuple = Depends(get_current_user_org)):
    """Delete a calendar event."""
    user, token, _org_id = auth
    db = get_user_client(token)

    delete_or_404(db, "eventos", ("id", event_id), ("user_id", str(user.id)), message="Evento nao encontrado")

    return ok_response("Evento removido")
