"""Content-draft routes — contract §B.5 (§A.6)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session.types import AuthContext

from app.auth.provenance import build_write_provenance
from app.dependencies import get_approval_assertion_keys, get_store, require_content_write, require_read
from app.knowledge import KnowledgeStore, KnowledgeStoreError
from app.routers._common import error_response

router = APIRouter(prefix="/api/content", tags=["content"])

Tipo = Literal["roteiro", "trilha", "quiz", "copy", "proposta", "outro"]

# Content types that need a source-backed `fontes` list — an empty list
# on one of these draws the §B.5 "aviso is returned when fontes is empty
# for roteiro, trilha or quiz" note.
_REQUIRES_FONTES: frozenset[str] = frozenset({"roteiro", "trilha", "quiz"})


class ContentCreate(StrictHttpModel):
    tipo: Tipo
    titulo: str = Field(min_length=1)
    corpo_md: str
    referencia: str | None = None
    fontes: list[str] | None = None


class ContentOut(BaseModel):
    codigo: str
    tipo: str
    titulo: str
    corpo_md: str
    referencia: str | None
    fontes: list[str]
    aviso: str | None = None


class ContentListOut(BaseModel):
    items: list[ContentOut]
    total: int


def _out(row: dict, *, aviso: str | None = None) -> ContentOut:
    return ContentOut(
        codigo=row["codigo"],
        tipo=row["tipo"],
        titulo=row["titulo"],
        corpo_md=row["corpo_md"],
        referencia=row.get("referencia"),
        fontes=list(row.get("fontes") or []),
        aviso=aviso,
    )


@router.get("", response_model=ContentListOut)
async def list_content(
    tipo: Tipo | None = Query(default=None),
    ctx: AuthContext = Depends(require_read),
    store: KnowledgeStore = Depends(get_store),
) -> ContentListOut:
    rows = await store.list_content(ctx.org_id, tipo=tipo)
    items = [_out(r) for r in rows]
    return ContentListOut(items=items, total=len(items))


@router.get("/{codigo}", response_model=ContentOut)
async def get_content(
    codigo: str,
    ctx: AuthContext = Depends(require_read),
    store: KnowledgeStore = Depends(get_store),
) -> ContentOut:
    try:
        row = await store.get_content(ctx.org_id, codigo)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    return _out(row)


@router.post("", response_model=ContentOut, status_code=status.HTTP_201_CREATED)
async def create_content(
    payload: ContentCreate,
    request: Request,
    ctx: AuthContext = Depends(require_content_write),
    keys: list[str] = Depends(get_approval_assertion_keys),
    store: KnowledgeStore = Depends(get_store),
) -> ContentOut:
    prov = await build_write_provenance(ctx, request, keys=keys)
    try:
        row = await store.create_content(ctx.org_id, payload.model_dump(), prov)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    aviso = (
        "Nenhuma fonte associada a este conteúdo."
        if row["tipo"] in _REQUIRES_FONTES and not row.get("fontes")
        else None
    )
    return _out(row, aviso=aviso)
