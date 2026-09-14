"""Roadmap + tasks routes — contract §B.4 (§A.4/§A.5).

Both entity types share one router (and one write scope,
`academia:roadmap:write` — §B.0 declares a single scope for the whole
B.4 section) because they are the same planning domain: phases group
tasks, and `/api/session-prep` reads across both.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session.types import AuthContext

from app.auth.provenance import build_write_provenance
from app.dependencies import get_approval_assertion_keys, get_store, require_roadmap_write, require_read
from app.knowledge import KnowledgeStore, KnowledgeStoreError
from app.routers._common import error_response
from app.routers.questions_router import QuestionOut, question_out

router = APIRouter(tags=["roadmap"])

Estado = Literal["pendente", "em-andamento", "concluida", "cancelada"]


# ─── Schemas ──────────────────────────────────────────────────────────


class PhaseUpdate(StrictHttpModel):
    estado: Estado | None = None
    titulo: str | None = None
    objetivo: str | None = None
    concluida_quando: str | None = None


class PhaseOut(BaseModel):
    codigo: str
    titulo: str
    objetivo: str
    concluida_quando: str | None = None
    estado: str
    ordem: int


class PhaseListOut(BaseModel):
    items: list[PhaseOut]
    total: int


class TaskCreate(StrictHttpModel):
    titulo: str = Field(min_length=1)
    fase: str = Field(min_length=1)
    detalhe: str | None = None
    bloqueada_por: str | None = None


class TaskUpdate(StrictHttpModel):
    estado: Estado | None = None
    detalhe: str | None = None
    bloqueada_por: str | None = None


class TaskOut(BaseModel):
    codigo: str
    titulo: str
    fase: str
    detalhe: str | None
    estado: str
    bloqueada_por: str | None


class TaskListOut(BaseModel):
    items: list[TaskOut]
    total: int


class SessionPrepOut(BaseModel):
    fase_atual: PhaseOut | None
    proximas: list[TaskOut]
    bloqueadas: list[TaskOut]
    perguntas_abertas: int
    perguntas_bloqueantes: list[QuestionOut]


def _phase_out(row: dict) -> PhaseOut:
    return PhaseOut(
        codigo=row["codigo"],
        titulo=row["titulo"],
        objetivo=row["objetivo"],
        concluida_quando=row.get("concluida_quando"),
        estado=row["estado"],
        ordem=row["ordem"],
    )


def _task_out(row: dict) -> TaskOut:
    return TaskOut(
        codigo=row["codigo"],
        titulo=row["titulo"],
        fase=row["fase"],
        detalhe=row.get("detalhe"),
        estado=row["estado"],
        bloqueada_por=row.get("bloqueada_por"),
    )


# ─── Roadmap phases ───────────────────────────────────────────────────


@router.get("/api/roadmap", response_model=PhaseListOut)
async def list_phases(
    ctx: AuthContext = Depends(require_read),
    store: KnowledgeStore = Depends(get_store),
) -> PhaseListOut:
    rows = await store.list_phases(ctx.org_id)
    items = [_phase_out(r) for r in rows]
    return PhaseListOut(items=items, total=len(items))


@router.patch("/api/roadmap/{codigo}", response_model=PhaseOut)
async def update_phase(
    codigo: str,
    payload: PhaseUpdate,
    request: Request,
    ctx: AuthContext = Depends(require_roadmap_write),
    keys: list[str] = Depends(get_approval_assertion_keys),
    store: KnowledgeStore = Depends(get_store),
) -> PhaseOut:
    prov = await build_write_provenance(ctx, request, keys=keys)
    changes = payload.model_dump(exclude_none=True)
    try:
        row = await store.update_phase(ctx.org_id, codigo, changes, prov)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    return _phase_out(row)


# ─── Tasks ────────────────────────────────────────────────────────────


@router.get("/api/tasks", response_model=TaskListOut)
async def list_tasks(
    fase: str | None = Query(default=None),
    estado: Estado | None = Query(default=None),
    ctx: AuthContext = Depends(require_read),
    store: KnowledgeStore = Depends(get_store),
) -> TaskListOut:
    rows = await store.list_tasks(ctx.org_id, fase=fase, estado=estado)
    items = [_task_out(r) for r in rows]
    return TaskListOut(items=items, total=len(items))


@router.post("/api/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    request: Request,
    ctx: AuthContext = Depends(require_roadmap_write),
    keys: list[str] = Depends(get_approval_assertion_keys),
    store: KnowledgeStore = Depends(get_store),
) -> TaskOut:
    prov = await build_write_provenance(ctx, request, keys=keys)
    try:
        row = await store.create_task(ctx.org_id, payload.model_dump(), prov)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    return _task_out(row)


@router.patch("/api/tasks/{codigo}", response_model=TaskOut)
async def update_task(
    codigo: str,
    payload: TaskUpdate,
    request: Request,
    ctx: AuthContext = Depends(require_roadmap_write),
    keys: list[str] = Depends(get_approval_assertion_keys),
    store: KnowledgeStore = Depends(get_store),
) -> TaskOut:
    prov = await build_write_provenance(ctx, request, keys=keys)
    changes = payload.model_dump(exclude_none=True)
    try:
        row = await store.update_task(ctx.org_id, codigo, changes, prov)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    return _task_out(row)


# ─── Session prep ─────────────────────────────────────────────────────


@router.get("/api/session-prep", response_model=SessionPrepOut)
async def session_prep(
    ctx: AuthContext = Depends(require_read),
    store: KnowledgeStore = Depends(get_store),
) -> SessionPrepOut:
    result = await store.session_prep(ctx.org_id)
    return SessionPrepOut(
        fase_atual=_phase_out(result["fase_atual"]) if result["fase_atual"] else None,
        proximas=[_task_out(t) for t in result["proximas"]],
        bloqueadas=[_task_out(t) for t in result["bloqueadas"]],
        perguntas_abertas=result["perguntas_abertas"],
        perguntas_bloqueantes=[question_out(q) for q in result["perguntas_bloqueantes"]],
    )
