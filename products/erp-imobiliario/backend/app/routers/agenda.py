"""
Agent Calendar / Agenda Router — event scheduling for corretores.

-- CREATE TABLE eventos (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   corretor_id uuid NOT NULL,
--   titulo text NOT NULL,
--   descricao text,
--   tipo text NOT NULL CHECK (tipo IN ('visita', 'reuniao', 'ligacao', 'vistoria', 'assinatura', 'outro')),
--   data_inicio timestamptz NOT NULL,
--   data_fim timestamptz NOT NULL,
--   local text,
--   cliente_id uuid,
--   imovel_id uuid,
--   status text NOT NULL DEFAULT 'agendado' CHECK (status IN ('agendado', 'confirmado', 'realizado', 'cancelado')),
--   cor text DEFAULT '#6366f1',
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings
from app.services.agenda_service import check_conflict

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agenda", tags=["Agenda"])

# Sao Paulo timezone offset (UTC-3)
SP_OFFSET = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class EventoCreate(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=200)
    descricao: Optional[str] = None
    tipo: Literal["visita", "reuniao", "ligacao", "vistoria", "assinatura", "outro"]
    data_inicio: str = Field(..., description="ISO 8601 datetime")
    data_fim: str = Field(..., description="ISO 8601 datetime")
    local: Optional[str] = None
    cliente_id: Optional[str] = None
    imovel_id: Optional[str] = None
    status: Literal["agendado", "confirmado", "realizado", "cancelado"] = "agendado"
    cor: str = "#6366f1"


class EventoUpdate(BaseModel):
    titulo: Optional[str] = Field(default=None, max_length=200)
    descricao: Optional[str] = None
    tipo: Optional[Literal["visita", "reuniao", "ligacao", "vistoria", "assinatura", "outro"]] = None
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    local: Optional[str] = None
    cliente_id: Optional[str] = None
    imovel_id: Optional[str] = None
    status: Optional[Literal["agendado", "confirmado", "realizado", "cancelado"]] = None
    cor: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today_range_sp():
    """Return ISO start/end of today in Sao Paulo time."""
    now_sp = datetime.now(SP_OFFSET)
    start = now_sp.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _week_range_sp():
    """Return ISO start/end of the current week (Mon-Sun) in Sao Paulo time."""
    now_sp = datetime.now(SP_OFFSET)
    start = (now_sp - timedelta(days=now_sp.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = start + timedelta(days=7)
    return start.isoformat(), end.isoformat()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def listar_eventos(
    data_inicio: Optional[str] = Query(None, description="Filter events starting from (ISO 8601)"),
    data_fim: Optional[str] = Query(None, description="Filter events ending before (ISO 8601)"),
    corretor_id: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    authorization: Optional[str] = Header(None),
):
    """List events with optional date range and corretor filters."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count
    count_query = db.table("eventos").select("id", count="exact")
    if data_inicio:
        count_query = count_query.gte("data_inicio", data_inicio)
    if data_fim:
        count_query = count_query.lte("data_fim", data_fim)
    if corretor_id:
        count_query = count_query.eq("corretor_id", corretor_id)
    if tipo:
        count_query = count_query.eq("tipo", tipo)
    if status:
        count_query = count_query.eq("status", status)
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data
    query = db.table("eventos").select("*").order("data_inicio", desc=False)
    if data_inicio:
        query = query.gte("data_inicio", data_inicio)
    if data_fim:
        query = query.lte("data_fim", data_fim)
    if corretor_id:
        query = query.eq("corretor_id", corretor_id)
    if tipo:
        query = query.eq("tipo", tipo)
    if status:
        query = query.eq("status", status)
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    return paginated_response(data, total, validated_page, validated_page_size)


@router.post("")
async def criar_evento(body: EventoCreate, authorization: Optional[str] = Header(None)):
    """Create a new calendar event. Warns if conflict detected."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Detect scheduling conflict
    conflito = check_conflict(user.id, body.data_inicio, body.data_fim, db)

    payload = body.model_dump()
    payload["corretor_id"] = user.id

    result = db.table("eventos").insert(payload).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar evento")

    evento = row
    log_action(user.id, "criar", "evento", evento["id"], f"Criou evento '{body.titulo}'")

    response_data = evento
    if conflito:
        response_data["_conflito"] = {
            "evento_id": conflito["id"],
            "titulo": conflito["titulo"],
            "mensagem": f"Conflito de horário com '{conflito['titulo']}'",
        }

    return success_response(response_data)


@router.get("/hoje")
async def eventos_hoje(authorization: Optional[str] = Header(None)):
    """Get today's events for the current user."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    start, end = _today_range_sp()

    result = db.table("eventos").select("*").eq(
        "corretor_id", user.id
    ).gte("data_inicio", start).lt("data_inicio", end).order(
        "data_inicio", desc=False
    ).execute()

    return success_response(result.data or [])


@router.get("/semana")
async def eventos_semana(authorization: Optional[str] = Header(None)):
    """Get this week's events for the current user."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    start, end = _week_range_sp()

    result = db.table("eventos").select("*").eq(
        "corretor_id", user.id
    ).gte("data_inicio", start).lt("data_inicio", end).order(
        "data_inicio", desc=False
    ).execute()

    return success_response(result.data or [])


@router.get("/{evento_id}")
async def obter_evento(evento_id: str, authorization: Optional[str] = Header(None)):
    """Get a single event."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("eventos").select("*").eq("id", evento_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    return success_response(result.data)


@router.patch("/{evento_id}")
async def atualizar_evento(
    evento_id: str, body: EventoUpdate, authorization: Optional[str] = Header(None)
):
    """Update an event. Warns if new time causes conflict."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Check conflict if dates changed
    conflito = None
    if "data_inicio" in data or "data_fim" in data:
        # Fetch existing event for fallback values
        existing = db.table("eventos").select("data_inicio, data_fim, corretor_id").eq(
            "id", evento_id
        ).single().execute()
        if existing.data:
            di = data.get("data_inicio", existing.data["data_inicio"])
            df = data.get("data_fim", existing.data["data_fim"])
            conflito = check_conflict(
                existing.data["corretor_id"], di, df, db, exclude_id=evento_id
            )

    result = db.table("eventos").update(data).eq("id", evento_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    log_action(user.id, "editar", "evento", evento_id, f"Editou evento {evento_id}")

    response_data = row
    if conflito:
        response_data["_conflito"] = {
            "evento_id": conflito["id"],
            "titulo": conflito["titulo"],
            "mensagem": f"Conflito de horário com '{conflito['titulo']}'",
        }

    return success_response(response_data)


@router.delete("/{evento_id}")
async def excluir_evento(evento_id: str, authorization: Optional[str] = Header(None)):
    """Delete an event."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    check = db.table("eventos").select("id").eq("id", evento_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    db.table("eventos").delete().eq("id", evento_id).execute()
    log_action(user.id, "excluir", "evento", evento_id, f"Excluiu evento {evento_id}")
    return ok_response("Evento excluído com sucesso")
