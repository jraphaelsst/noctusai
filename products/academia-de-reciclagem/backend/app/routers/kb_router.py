"""Knowledge base routes — contract §B.1.

`GET`/`POST`/`PUT`/archive/revisions over `kb_entries` (§A.1), backed by
the `KnowledgeStore` seam (§A.11). Every write is `motivo`-required
(§B.1's "Side-effect" note) and builds its `Provenance` via
`app.auth.provenance.build_write_provenance` (§D assertion verification
for non-`human_personal` product-token callers).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session.types import AuthContext

from app.auth.provenance import build_write_provenance
from app.dependencies import get_approval_assertion_keys, get_store, require_kb_write, require_read
from app.knowledge import KnowledgeStore, KnowledgeStoreError, NotFound
from app.routers._common import (
    RevisionOut,
    RevisionRefOut,
    error_response,
    revision_ref_out,
)

router = APIRouter(prefix="/api/kb", tags=["kb"])

Categoria = Literal[
    "contexto", "dominio", "instrucoes", "skills", "workflows",
    "mcp-servers", "historico", "marca", "evals", "geral",
]


def _slugify_kebab(label: str) -> str:
    """Kebab-case slug derivation (§B.1: "slug is derived from titulo
    when omitted"). Accent-folds so "Domínio Regulatório" -> "dominio-
    regulatorio", matching the sibling's own slug shape (§0's example:
    `dominio-regulatorio-pnrs`)."""
    folded = unicodedata.normalize("NFKD", label or "")
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug or "entrada"


# ─── Schemas ──────────────────────────────────────────────────────────


class KbEntryCreate(StrictHttpModel):
    slug: str | None = None
    categoria: Categoria
    subcategoria: str | None = None
    titulo: str = Field(min_length=1)
    resumo: str | None = None
    tags: list[str] | None = None
    corpo_md: str
    motivo: str = Field(min_length=1)


class KbEntryUpdate(StrictHttpModel):
    titulo: str | None = None
    resumo: str | None = None
    tags: list[str] | None = None
    corpo_md: str | None = None
    categoria: Categoria | None = None
    subcategoria: str | None = None
    novo_slug: str | None = None
    motivo: str = Field(min_length=1)


class KbEntryArchive(StrictHttpModel):
    motivo: str = Field(min_length=1)


class KbEntrySummaryOut(BaseModel):
    slug: str
    categoria: str
    subcategoria: str | None
    titulo: str
    resumo: str | None
    tags: list[str]
    updated_at: datetime


class KbEntryOut(KbEntrySummaryOut):
    corpo_md: str
    frontmatter: dict
    arquivado: bool
    current_revision: RevisionRefOut | None


class KbListOut(BaseModel):
    items: list[KbEntrySummaryOut]
    total: int


class RevisionListOut(BaseModel):
    items: list[RevisionOut]
    total: int


def _summary_out(row: dict) -> KbEntrySummaryOut:
    return KbEntrySummaryOut(
        slug=row["slug"],
        categoria=row["categoria"],
        subcategoria=row.get("subcategoria"),
        titulo=row["titulo"],
        resumo=row.get("resumo"),
        tags=list(row.get("tags") or []),
        updated_at=row["updated_at"],
    )


async def _entry_out(store: KnowledgeStore, org_id, row: dict) -> KbEntryOut:
    revisions = await store.list_revisions(org_id, "kb_entry", row["id"])
    return KbEntryOut(
        **_summary_out(row).model_dump(),
        corpo_md=row["corpo_md"],
        frontmatter=dict(row.get("frontmatter") or {}),
        arquivado=row["arquivado"],
        current_revision=revision_ref_out(revisions),
    )


# ─── Routes ───────────────────────────────────────────────────────────


@router.get("", response_model=KbListOut)
async def search_kb(
    consulta: str | None = Query(default=None),
    categoria: Categoria | None = Query(default=None),
    subcategoria: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    limite: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: AuthContext = Depends(require_read),
    store: KnowledgeStore = Depends(get_store),
) -> KbListOut:
    rows, total = await store.search_kb(
        ctx.org_id,
        consulta=consulta,
        categoria=categoria,
        subcategoria=subcategoria,
        tag=tag,
        limite=limite,
        offset=offset,
    )
    return KbListOut(items=[_summary_out(r) for r in rows], total=total)


@router.get("/{slug}", response_model=KbEntryOut)
async def get_kb(
    slug: str,
    ctx: AuthContext = Depends(require_read),
    store: KnowledgeStore = Depends(get_store),
) -> KbEntryOut:
    try:
        row = await store.get_kb(ctx.org_id, slug)
    except NotFound as exc:
        raise error_response(exc) from exc
    return await _entry_out(store, ctx.org_id, row)


@router.post("", response_model=KbEntryOut, status_code=status.HTTP_201_CREATED)
async def create_kb(
    payload: KbEntryCreate,
    request: Request,
    ctx: AuthContext = Depends(require_kb_write),
    keys: list[str] = Depends(get_approval_assertion_keys),
    store: KnowledgeStore = Depends(get_store),
) -> KbEntryOut:
    prov = await build_write_provenance(ctx, request, keys=keys, motivo=payload.motivo)
    data = payload.model_dump(exclude={"motivo"})
    data["slug"] = data.get("slug") or _slugify_kebab(payload.titulo)
    try:
        row = await store.create_kb(ctx.org_id, data, prov)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    return await _entry_out(store, ctx.org_id, row)


@router.put("/{slug}", response_model=KbEntryOut)
async def update_kb(
    slug: str,
    payload: KbEntryUpdate,
    request: Request,
    ctx: AuthContext = Depends(require_kb_write),
    keys: list[str] = Depends(get_approval_assertion_keys),
    store: KnowledgeStore = Depends(get_store),
) -> KbEntryOut:
    prov = await build_write_provenance(ctx, request, keys=keys, motivo=payload.motivo)
    changes = payload.model_dump(exclude={"motivo"}, exclude_none=True)
    try:
        row = await store.update_kb(ctx.org_id, slug, changes, prov)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    return await _entry_out(store, ctx.org_id, row)


@router.post("/{slug}/archive", response_model=KbEntryOut)
async def archive_kb(
    slug: str,
    payload: KbEntryArchive,
    request: Request,
    ctx: AuthContext = Depends(require_kb_write),
    keys: list[str] = Depends(get_approval_assertion_keys),
    store: KnowledgeStore = Depends(get_store),
) -> KbEntryOut:
    prov = await build_write_provenance(ctx, request, keys=keys, motivo=payload.motivo)
    try:
        row = await store.archive_kb(ctx.org_id, slug, prov)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc
    return await _entry_out(store, ctx.org_id, row)


@router.get("/{slug}/revisions", response_model=RevisionListOut)
async def list_kb_revisions(
    slug: str,
    ctx: AuthContext = Depends(require_read),
    store: KnowledgeStore = Depends(get_store),
) -> RevisionListOut:
    try:
        entry = await store.get_kb(ctx.org_id, slug)
    except NotFound as exc:
        raise error_response(exc) from exc
    revisions = await store.list_revisions(ctx.org_id, "kb_entry", entry["id"])
    items = [RevisionOut(**r) for r in revisions]
    return RevisionListOut(items=items, total=len(items))
