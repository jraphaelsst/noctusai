"""Timeline routes — contract §B.5 (§A.7).

CONTRACT NOTE (flagged in this slice's delivery note as a contract
defect): §B.0 lists 6 write scopes for the 7 write-domains in §B.1–§B.5
— there is no `academia:timeline:write`. Timeline is grouped with
content under §B.5, so this router reuses `academia:content:write`
(both are low-risk editorial writes, unlike `sources`, which accepts an
external URL and keeps its own scope).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session.types import AuthContext

from app.auth.provenance import build_write_provenance
from app.dependencies import get_approval_assertion_keys, get_store, require_content_write, require_read
from app.knowledge import KnowledgeStore, KnowledgeStoreError
from app.routers._common import error_response

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


class TimelineEventCreate(StrictHttpModel):
    titulo: str = Field(min_length=1)
    descricao: str = Field(min_length=1)
    data: date | None = None  # defaults server-side to today


class TimelineEventOut(BaseModel):
    data: str
    titulo: str
    descricao: str


class TimelineListOut(BaseModel):
    items: list[TimelineEventOut]
    total: int


def _out(row: dict) -> TimelineEventOut:
    data = row["data"]
    return TimelineEventOut(
        data=data.isoformat() if hasattr(data, "isoformat") else str(data),
        titulo=row["titulo"],
        descricao=row["descricao"],
    )


@router.get("", response_model=TimelineListOut)
async def list_timeline(
    limite: int = Query(default=20, ge=1, le=500),
    ctx: AuthContext = Depends(require_read),
    store: KnowledgeStore = Depends(get_store),
) -> TimelineListOut:
    rows = await store.list_timeline(ctx.org_id, limite=limite)
    items = [_out(r) for r in rows]
    return TimelineListOut(items=items, total=len(items))


@router.post("", response_model=TimelineEventOut, status_code=status.HTTP_201_CREATED)
async def create_timeline_event(
    payload: TimelineEventCreate,
    request: Request,
    ctx: AuthContext = Depends(require_content_write),
    keys: list[str] = Depends(get_approval_assertion_keys),
    store: KnowledgeStore = Depends(get_store),
) -> TimelineEventOut:
    prov = await build_write_provenance(ctx, request, keys=keys)
    try:
        row = await store.create_timeline_event(ctx.org_id, payload.model_dump(), prov)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    return _out(row)
