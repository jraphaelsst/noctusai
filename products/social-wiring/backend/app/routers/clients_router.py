"""Clients CRUD router — /api/clients.

Endpoints:
    GET    /api/clients          → Client[]
    POST   /api/clients          → Client (201)
    PATCH  /api/clients/{id}     → Client
    DELETE /api/clients/{id}     → 204

Auth: ``Depends(get_current_user_org)`` throughout. Admin client used for
all writes (service-role, same shape as integration_accounts_router).

``clients`` is the canonical entity that folds in ``mc_brand_owners``
(migration 007). It anchors per-account channel objects via the
``integration_accounts.client_id`` FK (migration 008).
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
from app.services.clients_service import (
    Client,
    ClientNotFound,
    ClientService,
    build_client_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clients", tags=["clients"])


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class ClientOut(BaseModel):
    """REST-safe representation of a client row."""

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


class ClientCreate(BaseModel):
    """POST /api/clients body."""

    slug: str
    name: str
    kind: str = "real_estate_agent"
    notes: Optional[str] = None

    class Config:
        extra = "forbid"


class ClientUpdate(BaseModel):
    """PATCH /api/clients/{id} body — all fields optional."""

    name: Optional[str] = None
    slug: Optional[str] = None
    kind: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        extra = "forbid"


# ─── DI seam ─────────────────────────────────────────────────────────────────

def get_client_service() -> ClientService:
    """Yield a wired ClientService backed by the admin Supabase client.

    Tests override via ``app.dependency_overrides[get_client_service]``.
    Per KB § PATTERNS/di-test-seam.md (Class-B, service DI).
    """
    return build_client_service(get_admin_client())


# ─── helpers ─────────────────────────────────────────────────────────────────

def _out(client: Client) -> ClientOut:
    return ClientOut(
        id=client.id,
        org_id=client.org_id,
        slug=client.slug,
        name=client.name,
        kind=client.kind,
        notes=client.notes,
        created_at=client.created_at,
        updated_at=client.updated_at,
    )


def _require_client(svc: ClientService, client_id: UUID, org_id: UUID) -> Client:
    """Fetch a client owner-scoped or 404."""
    c = svc.get_client(client_id, org_id)
    if c is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="client not found",
        )
    return c


# ─── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ClientOut])
def list_clients(
    auth: tuple = Depends(get_current_user_org),
    svc: ClientService = Depends(get_client_service),
) -> list[ClientOut]:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    clients = svc.list_clients(org_id=org_id)
    return [_out(c) for c in clients]


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    body: ClientCreate,
    auth: tuple = Depends(get_current_user_org),
    svc: ClientService = Depends(get_client_service),
) -> ClientOut:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        client = svc.create_client(
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
                detail=f"a client with slug {body.slug!r} already exists for this org",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"client create failed: {exc}",
        ) from exc
    return _out(client)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: UUID,
    body: ClientUpdate,
    auth: tuple = Depends(get_current_user_org),
    svc: ClientService = Depends(get_client_service),
) -> ClientOut:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    _require_client(svc, client_id, org_id)
    try:
        client = svc.update_client(
            client_id=client_id,
            org_id=org_id,
            name=body.name,
            slug=body.slug,
            kind=body.kind,
            notes=body.notes,
        )
    except ClientNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="client not found",
        )
    return _out(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    svc: ClientService = Depends(get_client_service),
) -> Response:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    deleted = svc.delete_client(client_id=client_id, org_id=org_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="client not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
