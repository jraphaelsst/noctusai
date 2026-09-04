"""Imóveis router — /api/imoveis.

Endpoints:
    GET  /api/imoveis                  → paginated rows from the local mirror
    GET  /api/imoveis/filtros          → distinct filter values (derived)
    GET  /api/imoveis/caracteristicas  → amenity slug → count, usage-ordered
    GET  /api/imoveis/{codigo}         → one imóvel
    POST /api/imoveis/sync             → full pull from Vista (D1 manual refresh)

Auth: ``Depends(get_current_user_org)`` on every route, no exceptions. Reads
go through the admin client with an explicit `org_id` filter — defense in
depth on top of RLS.

Reads hit `social_wiring.imoveis`, never Vista. Only `/sync` talks to the
CRM, and it is the write path.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
)
from app.services.imoveis_service import (
    build_imoveis_service,
    build_sync_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/imoveis", tags=["imoveis"])


# ─── Schemas ──────────────────────────────────────────────────────────────


class ImovelPageOut(BaseModel):
    """`items` is deliberately `list[dict]`, not a per-field imóvel schema.

    The service already selects `*` and returns rows straight through, now
    including the 29 fields + the two presentation-only derived values
    (`orientacao_solar`, `dias_desde_atualizacao`) from CONTRACT §1/§3
    (`imoveis-vista-field-surface`). A hand-maintained field allowlist here
    would have to grow in lockstep with every future Vista column and would
    silently drop one the moment it didn't — the exact "hand-maintained
    list drifts" failure mode CLAUDE.md §1 calls out. Nothing narrows the
    row between the service and the client.
    """

    items: list[dict] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    pages: int = 1


class FiltrosOut(BaseModel):
    status: list[str] = Field(default_factory=list)
    categoria: list[str] = Field(default_factory=list)
    cidade: list[str] = Field(default_factory=list)
    bairro: list[str] = Field(default_factory=list)


class SyncOut(BaseModel):
    """The sync result, including what it did NOT manage to do.

    `complete` is false whenever any page or any detalhes call failed, and
    `detalhes_failed` names the imóveis. A sync that reported only a success
    count would let a partial run look identical to a clean one — and the
    imóveis missing their detalhes are exactly the ones that silently drop
    out of amenity filters.
    """

    total_reported: int
    pages_fetched: int
    upserted: int
    detalhes_fetched: int
    detalhes_failed: list[str]
    detalhes_failed_count: int
    page_failures: list[str]
    complete: bool
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: float = 0.0


# ─── Routes ───────────────────────────────────────────────────────────────


@router.get("", response_model=ImovelPageOut)
async def list_imoveis(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    status_: Optional[str] = Query(None, alias="status"),
    categoria: Optional[str] = None,
    cidade: Optional[str] = None,
    bairro: Optional[str] = None,
    search: Optional[str] = None,
    caracteristicas: Optional[list[str]] = Query(None),
    auth=Depends(get_current_user_org),
    db=Depends(get_admin_client),
) -> ImovelPageOut:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    result = build_imoveis_service(db).list(
        org_id,
        page=page,
        page_size=page_size,
        status=status_,
        categoria=categoria,
        cidade=cidade,
        bairro=bairro,
        search=search,
        caracteristicas=caracteristicas,
    )
    return ImovelPageOut(**result)


@router.get("/filtros", response_model=FiltrosOut)
async def get_filtros(
    auth=Depends(get_current_user_org),
    db=Depends(get_admin_client),
) -> FiltrosOut:
    """Filter dropdown values, derived from stored rows — never hardcoded."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return FiltrosOut(**build_imoveis_service(db).filter_options(org_id))


@router.get("/caracteristicas")
async def get_caracteristicas(
    auth=Depends(get_current_user_org),
    db=Depends(get_admin_client),
) -> dict[str, int]:
    """Amenity slug → imóvel count, usage-ordered.

    The UI orders filters by this and drops the zeroes — the census found 28
    of the 76 tenant keys are never `Sim`, and showing them would be 28
    filters that always return nothing.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return build_imoveis_service(db).caracteristica_counts(org_id)


@router.post("/sync", response_model=SyncOut)
async def sync_imoveis(
    with_detalhes: bool = Query(
        True,
        description=(
            "Fetch per-imóvel detalhes (~1 extra call each, ~4-6 min for the "
            "full catalog). Required for caracteristicas + finalidades, both "
            "of which are detalhes-only on the wire."
        ),
    ),
    auth=Depends(get_current_user_org),
    db=Depends(get_admin_client),
) -> SyncOut:
    """Full pull from Vista. Idempotent — upserts by (org_id, codigo)."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    # Import here, not at module scope: the adapter raises when Vista is
    # unconfigured, and an import-time raise would take the whole app down
    # on a deploy where Vista simply isn't wired yet.
    from noctusai_lib.integrations.vista import (
        VistaNotConfigured,
        VistaRESTAdapter,
    )

    try:
        adapter = VistaRESTAdapter(
            base_url=settings.crm_base_url,
            api_key=settings.crm_api_key,
        )
    except VistaNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Vista não configurado: {exc}",
        ) from exc

    report = await build_sync_service(db, adapter).sync(
        org_id, with_detalhes=with_detalhes
    )
    return SyncOut(**report.as_dict())


# Declared LAST: `/{codigo}` would otherwise shadow `/filtros`,
# `/caracteristicas` and `/sync`, since FastAPI matches in declaration order
# and a bare path segment is a valid `codigo`.
#
# `-> dict`, no `response_model`, DELIBERATELY — same reasoning as
# `ImovelPageOut.items` above: `ImoveisService.get` already returns every
# column plus the derived `orientacao_solar`/`dias_desde_atualizacao`
# (CONTRACT §3), and a typed schema here would just be a second field list
# to keep in sync with the first. DISPLAY ONLY: no PATCH/PUT route exists on
# this router and none should be added — Vista rejects writes on this key
# (`/imoveis/alterar` → 404 on this tenant, CONTRACT §"Scope").
@router.get("/{codigo}")
async def get_imovel(
    codigo: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_admin_client),
) -> dict:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    row = build_imoveis_service(db).get(org_id, codigo.upper())
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Imóvel {codigo} não encontrado.",
        )
    return row
