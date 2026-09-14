"""Open-question routes — contract §B.3 (§A.3)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session.types import AuthContext

from app.auth.provenance import build_write_provenance
from app.dependencies import get_approval_assertion_keys, get_store, require_questions_write, require_read
from app.knowledge import KnowledgeStore, KnowledgeStoreError
from app.routers._common import error_response

router = APIRouter(prefix="/api/questions", tags=["questions"])

Estado = Literal["aberta", "respondida", "todas"]


class QuestionCreate(StrictHttpModel):
    pergunta: str = Field(min_length=1)
    por_que_importa: str = Field(min_length=1)
    bloqueia: bool
    destino_kb: str | None = None


class QuestionAnswer(StrictHttpModel):
    resposta: str = Field(min_length=1)


class QuestionOut(BaseModel):
    codigo: str
    pergunta: str
    por_que_importa: str
    bloqueia: bool
    destino_kb: str | None
    estado: str
    resposta: str | None
    respondida_em: datetime | None
    aviso: str | None = None


class QuestionListOut(BaseModel):
    items: list[QuestionOut]
    total: int


def question_out(row: dict, *, aviso: str | None = None) -> QuestionOut:
    return QuestionOut(
        codigo=row["codigo"],
        pergunta=row["pergunta"],
        por_que_importa=row["por_que_importa"],
        bloqueia=row["bloqueia"],
        destino_kb=row.get("destino_kb"),
        estado=row["estado"],
        resposta=row.get("resposta"),
        respondida_em=row.get("respondida_em"),
        aviso=aviso,
    )


@router.get("", response_model=QuestionListOut)
async def list_questions(
    estado: Estado = Query(default="aberta"),
    ctx: AuthContext = Depends(require_read),
    store: KnowledgeStore = Depends(get_store),
) -> QuestionListOut:
    rows = await store.list_questions(ctx.org_id, estado=estado)
    items = [question_out(r) for r in rows]
    return QuestionListOut(items=items, total=len(items))


@router.post("", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
async def create_question(
    payload: QuestionCreate,
    request: Request,
    ctx: AuthContext = Depends(require_questions_write),
    keys: list[str] = Depends(get_approval_assertion_keys),
    store: KnowledgeStore = Depends(get_store),
) -> QuestionOut:
    prov = await build_write_provenance(ctx, request, keys=keys)
    try:
        row = await store.create_question(ctx.org_id, payload.model_dump(), prov)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    return question_out(row)


@router.post("/{codigo}/answer", response_model=QuestionOut)
async def answer_question(
    codigo: str,
    payload: QuestionAnswer,
    request: Request,
    ctx: AuthContext = Depends(require_questions_write),
    keys: list[str] = Depends(get_approval_assertion_keys),
    store: KnowledgeStore = Depends(get_store),
) -> QuestionOut:
    prov = await build_write_provenance(ctx, request, keys=keys)
    try:
        row = await store.answer_question(ctx.org_id, codigo, payload.resposta, prov)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    aviso = (
        f"Registre a resposta em /kb/{row['destino_kb']}"
        if row.get("destino_kb")
        else None
    )
    return question_out(row, aviso=aviso)
