"""Marcas CRUD router — /api/marcas.

Endpoints:
    GET    /api/marcas          → Marca[]
    POST   /api/marcas          → Marca (201)
    PATCH  /api/marcas/{id}     → Marca
    DELETE /api/marcas/{id}     → 204

Auth: ``Depends(get_current_user_org)`` throughout. Admin client used for
all writes (service-role, same shape as integration_accounts_router).

``marcas`` is the canonical entity that folds in ``mc_brand_owners``
(renamed from ``clients`` by migration 046 — roadmap Phase 0)
(migration 007). It anchors per-account channel objects via the
``integration_accounts.marca_id`` FK (migration 008).
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
)
from app.services.marcas_service import (
    Marca,
    MarcaNotFound,
    MarcaService,
    build_marca_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marcas", tags=["marcas"])


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class MarcaOut(BaseModel):
    """REST-safe representation of a marca row."""

    id: UUID
    org_id: UUID
    slug: str
    name: str
    kind: str
    notes: Optional[str] = None
    created_at: Any = None
    updated_at: Any = None

    class Config:
        from_attributes = True


class MarcaCreate(BaseModel):
    """POST /api/marcas body."""

    slug: str
    name: str
    kind: str = "real_estate_agent"
    notes: Optional[str] = None

    class Config:
        extra = "forbid"


class MarcaUpdate(BaseModel):
    """PATCH /api/marcas/{id} body — all fields optional."""

    name: Optional[str] = None
    slug: Optional[str] = None
    kind: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        extra = "forbid"


# ─── DI seam ─────────────────────────────────────────────────────────────────

def get_marca_service() -> MarcaService:
    """Yield a wired MarcaService backed by the admin Supabase client.

    Tests override via ``app.dependency_overrides[get_marca_service]``.
    Per KB § PATTERNS/di-test-seam.md (Class-B, service DI).
    """
    return build_marca_service(get_admin_client())


# ─── helpers ─────────────────────────────────────────────────────────────────

def _out(marca: Marca) -> MarcaOut:
    return MarcaOut(
        id=marca.id,
        org_id=marca.org_id,
        slug=marca.slug,
        name=marca.name,
        kind=marca.kind,
        notes=marca.notes,
        created_at=marca.created_at,
        updated_at=marca.updated_at,
    )


def _require_marca(svc: MarcaService, marca_id: UUID, org_id: UUID) -> Marca:
    """Fetch a marca owner-scoped or 404."""
    c = svc.get_marca(marca_id, org_id)
    if c is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="marca not found",
        )
    return c


# ─── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[MarcaOut])
def list_marcas(
    auth: tuple = Depends(get_current_user_org),
    svc: MarcaService = Depends(get_marca_service),
) -> list[MarcaOut]:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    marcas = svc.list_marcas(org_id=org_id)
    return [_out(m) for m in marcas]


@router.get("/{marca_id}", response_model=MarcaOut)
def get_marca(
    marca_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    svc: MarcaService = Depends(get_marca_service),
) -> MarcaOut:
    """Fetch one marca.

    Completes the CRUD surface: list / create / update / delete all existed,
    read-one did not, so `useMarca(id)` on the frontend could only ever 404.
    Declared AFTER the collection routes and before the `{marca_id}` mutators
    so the literal `""` path is never shadowed.
    """
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return _out(_require_marca(svc, marca_id, org_id))


@router.post("", response_model=MarcaOut, status_code=status.HTTP_201_CREATED)
def create_marca(
    body: MarcaCreate,
    auth: tuple = Depends(get_current_user_org),
    svc: MarcaService = Depends(get_marca_service),
) -> MarcaOut:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        marca = svc.create_marca(
            org_id=org_id,
            slug=body.slug,
            name=body.name,
            kind=body.kind,
            notes=body.notes,
        )
    except Exception as exc:
        # Unique-constraint violation (org_id, slug) surfaces as a 409.
        msg = str(exc).lower()
        if "unique" in msg or "conflict" in msg or "duplicate" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"a marca with slug {body.slug!r} already exists for this org",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"marca create failed: {exc}",
        ) from exc
    return _out(marca)


@router.patch("/{marca_id}", response_model=MarcaOut)
def update_marca(
    marca_id: UUID,
    body: MarcaUpdate,
    auth: tuple = Depends(get_current_user_org),
    svc: MarcaService = Depends(get_marca_service),
) -> MarcaOut:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    _require_marca(svc, marca_id, org_id)
    try:
        marca = svc.update_marca(
            marca_id=marca_id,
            org_id=org_id,
            name=body.name,
            slug=body.slug,
            kind=body.kind,
            notes=body.notes,
        )
    except MarcaNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="marca not found",
        )
    return _out(marca)


@router.delete("/{marca_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_marca(
    marca_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    svc: MarcaService = Depends(get_marca_service),
) -> Response:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    deleted = svc.delete_marca(marca_id=marca_id, org_id=org_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="marca not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
