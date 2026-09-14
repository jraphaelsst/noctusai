"""Decision-log routes — contract §B.2 (append-only, §A.2)."""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session.types import AuthContext

from app.auth.provenance import build_write_provenance
from app.dependencies import get_approval_assertion_keys, get_store, require_decisions_write, require_read
from app.knowledge import KnowledgeStore, KnowledgeStoreError
from app.routers._common import error_response

router = APIRouter(prefix="/api/decisions", tags=["decisions"])

Estado = Literal["vigente", "superseded"]


class DecisionCreate(StrictHttpModel):
    titulo: str = Field(min_length=1)
    contexto: str | None = None
    decisao: str = Field(min_length=1)
    motivo: str = Field(min_length=1)
    alternativas_rejeitadas: str | None = None
    relacionadas: list[str] | None = None


class DecisionOut(BaseModel):
    codigo: str
    titulo: str
    contexto: str | None
    decisao: str
    motivo: str
    alternativas_rejeitadas: str | None
    data: date
    estado: str
    substitui: str | None
    superseded_by: str | None
    relacionadas: list[str]


class DecisionListOut(BaseModel):
    items: list[DecisionOut]
    total: int


class SupersedeOut(BaseModel):
    nova: DecisionOut
    substituida: DecisionOut


def _out(row: dict) -> DecisionOut:
    return DecisionOut(
        codigo=row["codigo"],
        titulo=row["titulo"],
        contexto=row.get("contexto"),
        decisao=row["decisao"],
        motivo=row["motivo"],
        alternativas_rejeitadas=row.get("alternativas_rejeitadas"),
        data=row["data"],
        estado=row["estado"],
        substitui=row.get("substitui"),
        superseded_by=row.get("superseded_by"),
        relacionadas=list(row.get("relacionadas") or []),
    )


@router.get("", response_model=DecisionListOut)
async def list_decisions(
    estado: Estado | None = Query(default=None),
    ctx: AuthContext = Depends(require_read),
    store: KnowledgeStore = Depends(get_store),
) -> DecisionListOut:
    rows = await store.list_decisions(ctx.org_id, estado=estado)
    items = [_out(r) for r in rows]
    return DecisionListOut(items=items, total=len(items))


@router.get("/{codigo}", response_model=DecisionOut)
async def get_decision(
    codigo: str,
    ctx: AuthContext = Depends(require_read),
    store: KnowledgeStore = Depends(get_store),
) -> DecisionOut:
    try:
        row = await store.get_decision(ctx.org_id, codigo)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    return _out(row)


@router.post("", response_model=DecisionOut, status_code=status.HTTP_201_CREATED)
async def create_decision(
    payload: DecisionCreate,
    request: Request,
    ctx: AuthContext = Depends(require_decisions_write),
    keys: list[str] = Depends(get_approval_assertion_keys),
    store: KnowledgeStore = Depends(get_store),
) -> DecisionOut:
    prov = await build_write_provenance(ctx, request, keys=keys)
    try:
        row = await store.create_decision(ctx.org_id, payload.model_dump(), prov)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    return _out(row)


@router.post(
    "/{codigo}/supersede", response_model=SupersedeOut, status_code=status.HTTP_201_CREATED
)
async def supersede_decision(
    codigo: str,
    payload: DecisionCreate,
    request: Request,
    ctx: AuthContext = Depends(require_decisions_write),
    keys: list[str] = Depends(get_approval_assertion_keys),
    store: KnowledgeStore = Depends(get_store),
) -> SupersedeOut:
    prov = await build_write_provenance(ctx, request, keys=keys)
    try:
        nova, substituida = await store.supersede_decision(
            ctx.org_id, codigo, payload.model_dump(), prov
        )
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    return SupersedeOut(nova=_out(nova), substituida=_out(substituida))
