"""
Tasks Router — Personal task management for Daily Life.

CRUD for tasks with priorities, due dates, categories, and status tracking.
Supports both individual and org-scoped tasks.
"""
import logging
from typing import Optional
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from app.dependencies import get_user_client, get_current_user_org
from app.services.tasks_service import get_prioridade_ordem, compute_task_stats
from noctusai_lib.primitives.responses import success_response, paginated_response, ok_response
from noctusai_lib.api.auth import first_or_none

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TaskCreate(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=300)
    descricao: Optional[str] = None
    prioridade: str = Field(default="media", pattern="^(alta|media|baixa)$")
    categoria: Optional[str] = None
    data_vencimento: Optional[date] = None


class TaskUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=1, max_length=300)
    descricao: Optional[str] = None
    prioridade: Optional[str] = Field(None, pattern="^(alta|media|baixa)$")
    categoria: Optional[str] = None
    data_vencimento: Optional[date] = None
    status: Optional[str] = Field(None, pattern="^(pendente|em_progresso|concluida|cancelada)$")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def listar_tarefas(
    auth: tuple = Depends(get_current_user_org),
    status: Optional[str] = Query(None),
    prioridade: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List user tasks with optional filters."""
    user, token, _org_id = auth
    db = get_user_client(token)

    query = db.table("tarefas").select("*", count="exact").eq("user_id", str(user.id))

    if status:
        query = query.eq("status", status)
    if prioridade:
        query = query.eq("prioridade", prioridade)
    if categoria:
        query = query.eq("categoria", categoria)

    query = query.order("data_vencimento", desc=False).order("prioridade_ordem", desc=True)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return paginated_response(result.data or [], result.count or 0, page, page_size)


@router.post("")
async def criar_tarefa(body: TaskCreate, auth: tuple = Depends(get_current_user_org)):
    """Create a new task."""
    user, token, org_id = auth
    db = get_user_client(token)

    result = db.table("tarefas").insert({
        "user_id": str(user.id),
        "org_id": org_id,
        "titulo": body.titulo,
        "descricao": body.descricao,
        "prioridade": body.prioridade,
        "prioridade_ordem": get_prioridade_ordem(body.prioridade),
        "categoria": body.categoria,
        "data_vencimento": str(body.data_vencimento) if body.data_vencimento else None,
        "status": "pendente",
    }).execute()

    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar tarefa")

    return success_response(row)


@router.get("/{task_id}")
async def obter_tarefa(task_id: str, auth: tuple = Depends(get_current_user_org)):
    """Get a single task by ID."""
    user, token, _org_id = auth
    db = get_user_client(token)

    result = (
        db.table("tarefas")
        .select("*")
        .eq("id", task_id)
        .eq("user_id", str(user.id))
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Tarefa nao encontrada")

    return success_response(row)


@router.patch("/{task_id}")
async def atualizar_tarefa(task_id: str, body: TaskUpdate, auth: tuple = Depends(get_current_user_org)):
    """Update an existing task."""
    user, token, _org_id = auth
    db = get_user_client(token)

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    if "prioridade" in updates:
        updates["prioridade_ordem"] = get_prioridade_ordem(updates["prioridade"])

    if "data_vencimento" in updates and updates["data_vencimento"]:
        updates["data_vencimento"] = str(updates["data_vencimento"])

    result = (
        db.table("tarefas")
        .update(updates)
        .eq("id", task_id)
        .eq("user_id", str(user.id))
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Tarefa nao encontrada")

    return success_response(row)


@router.delete("/{task_id}")
async def deletar_tarefa(task_id: str, auth: tuple = Depends(get_current_user_org)):
    """Delete a task."""
    user, token, _org_id = auth
    db = get_user_client(token)

    result = (
        db.table("tarefas")
        .delete()
        .eq("id", task_id)
        .eq("user_id", str(user.id))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Tarefa nao encontrada")

    return ok_response("Tarefa removida")


@router.get("/stats/resumo")
async def resumo_tarefas(auth: tuple = Depends(get_current_user_org)):
    """Get task statistics for the current user."""
    user, token, _org_id = auth
    db = get_user_client(token)

    result = db.table("tarefas").select("status", count="exact").eq("user_id", str(user.id)).execute()
    stats = compute_task_stats(result.data or [])

    return success_response(stats)
