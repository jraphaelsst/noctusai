"""Portal ROI router — /api/portal-roi.

Endpoints (contract: ``portal-roi-PROJECT.md`` §3):
    GET    /api/portal-roi/resumo      → per-portal + platform totals
    GET    /api/portal-roi/campanhas   → spend rows, newest period first
    POST   /api/portal-roi/campanhas   → create a spend entry (201)
    PATCH  /api/portal-roi/campanhas/{id}
    DELETE /api/portal-roi/campanhas/{id}
    GET    /api/portal-roi/origens     → lead_sources picker feed

Auth: ``Depends(get_current_user_org)`` on every route, no exceptions —
``org_id`` always comes from the auth context, never a client parameter
(contract §3, non-negotiable). Mirrors ``imoveis_router.py``'s shape.

Error mapping is mostly IMPLICIT: ``NotFoundError`` / ``ConflictError`` /
``PortalRoiValidationError`` all subclass ``AppException``, which
``create_product_app`` already wires an exception handler for
(``app.add_exception_handler(AppException, ...)``, MRO-dispatched) — the
service raises, the platform-wide handler converts to the right status +
an actionable ``{"error": {...}}`` body. No router-level try/except
needed for those three. GENERATED-column rejection (``cpc``/``cpl``/
``custo_visita`` -> 422) is likewise implicit: those fields are simply
never declared on the write schemas below, so ``StrictHttpModel``'s
``extra="forbid"`` 422s automatically the moment a caller sends one.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.primitives.exceptions import NotFoundError

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.services.portal_roi_service import (
    build_portal_roi_service,
    get_portal_roi_client,
)

router = APIRouter(prefix="/api/portal-roi", tags=["portal-roi"])


# ─── Schemas ──────────────────────────────────────────────────────────────


class PeriodoOut(BaseModel):
    inicio: Optional[str] = None
    fim: Optional[str] = None


class TotaisOut(BaseModel):
    investimento: Optional[float] = None
    total_leads: int = 0
    total_vendas: int = 0
    valor_vendas: float = 0
    cpl: Optional[float] = None
    roi: Optional[float] = None
    taxa_conversao: Optional[float] = None


class PortalOut(BaseModel):
    origem_id: UUID
    slug: str
    label: str
    categoria: str
    # 🔴 `null` (unrecorded) and `0` (recorded zero) are different facts —
    # never coerce one into the other. See portal_roi_service.py + `047`.
    investimento: Optional[float] = None
    total_leads: int = 0
    total_vendas: int = 0
    valor_vendas: float = 0
    cpl: Optional[float] = None
    roi: Optional[float] = None
    taxa_conversao: Optional[float] = None


class ResumoOut(BaseModel):
    periodo: Optional[PeriodoOut] = None
    totais: TotaisOut
    portais: list[PortalOut] = Field(default_factory=list)


class CampanhaOut(BaseModel):
    id: UUID
    origem_id: UUID
    origem_label: str
    periodo_inicio: date
    periodo_fim: date
    investimento: float
    impressoes: Optional[int] = None
    cliques: Optional[int] = None
    leads: Optional[int] = None
    visitas_perfil: Optional[int] = None
    engajamento: Optional[int] = None
    # GENERATED (read-only) — computed by portal_roi_service, never
    # accepted on write (see the Create/Update schemas below).
    cpc: Optional[float] = None
    cpl: Optional[float] = None
    custo_visita: Optional[float] = None
    observacoes: Optional[str] = None
    created_at: Any = None
    updated_at: Any = None

    model_config = ConfigDict(from_attributes=True)


class CampanhasOut(BaseModel):
    campanhas: list[CampanhaOut] = Field(default_factory=list)


class LeadCampanhaCreate(StrictHttpModel):
    """POST /api/portal-roi/campanhas body.

    `cpc`/`cpl`/`custo_visita` are deliberately NOT fields here — naming
    one in the request body 422s via `StrictHttpModel`'s `extra="forbid"`
    (contract §3.3: "reject a write that names them, never silently
    drop it")."""

    origem_id: UUID
    periodo_inicio: date
    periodo_fim: date
    investimento: float = 0
    impressoes: Optional[int] = None
    cliques: Optional[int] = None
    leads: Optional[int] = None
    visitas_perfil: Optional[int] = None
    engajamento: Optional[int] = None
    observacoes: Optional[str] = None


class LeadCampanhaUpdate(StrictHttpModel):
    """PATCH /api/portal-roi/campanhas/{id} body — all fields optional.

    Router calls the service with ``model_dump(exclude_unset=True)`` —
    a key's PRESENCE means the caller explicitly sent it, mirroring
    ``app/modules/leads/routers/sources.py``'s PATCH contract."""

    origem_id: Optional[UUID] = None
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None
    investimento: Optional[float] = None
    impressoes: Optional[int] = None
    cliques: Optional[int] = None
    leads: Optional[int] = None
    visitas_perfil: Optional[int] = None
    engajamento: Optional[int] = None
    observacoes: Optional[str] = None


class DeletedOut(BaseModel):
    deleted: bool
    id: UUID


class OrigemOut(BaseModel):
    id: UUID
    slug: str
    label: str
    categoria: str


class OrigensOut(BaseModel):
    origens: list[OrigemOut] = Field(default_factory=list)


# ─── DI seam ─────────────────────────────────────────────────────────────


def get_portal_roi_service():
    """Tests override via ``app.dependency_overrides[get_portal_roi_service]``.
    Per KB § PATTERNS/di-test-seam.md (Class-B, service DI)."""
    return build_portal_roi_service(get_portal_roi_client())


# ─── Routes ───────────────────────────────────────────────────────────────
#
# `/campanhas/{campanha_id}` is declared before `/origens` and after the
# bare `/campanhas` collection routes — no ambiguous bare-segment catch-all
# exists on this router (every static path is a fixed literal segment:
# `resumo`, `campanhas`, `origens`), so — unlike `imoveis_router.py`'s
# `/{codigo}` — there is no route-ordering hazard here to guard against.


@router.get("/resumo", response_model=ResumoOut)
async def get_resumo(
    periodo_inicio: Optional[date] = Query(None),
    periodo_fim: Optional[date] = Query(None),
    auth=Depends(get_current_user_org),
    svc=Depends(get_portal_roi_service),
) -> ResumoOut:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return ResumoOut(**svc.resumo(org_id, periodo_inicio, periodo_fim))


@router.get("/campanhas", response_model=CampanhasOut)
async def list_campanhas(
    origem_id: Optional[UUID] = Query(None),
    periodo_inicio: Optional[date] = Query(None),
    periodo_fim: Optional[date] = Query(None),
    auth=Depends(get_current_user_org),
    svc=Depends(get_portal_roi_service),
) -> CampanhasOut:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    rows = svc.list_campanhas(
        org_id,
        origem_id=origem_id,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
    )
    return CampanhasOut(campanhas=rows)


@router.post("/campanhas", response_model=CampanhaOut, status_code=status.HTTP_201_CREATED)
async def create_campanha(
    body: LeadCampanhaCreate,
    auth=Depends(get_current_user_org),
    svc=Depends(get_portal_roi_service),
) -> CampanhaOut:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    row = svc.create_campanha(org_id, **body.model_dump())
    return CampanhaOut(**row)


@router.patch("/campanhas/{campanha_id}", response_model=CampanhaOut)
async def update_campanha(
    campanha_id: UUID,
    body: LeadCampanhaUpdate,
    auth=Depends(get_current_user_org),
    svc=Depends(get_portal_roi_service),
) -> CampanhaOut:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    row = svc.update_campanha(org_id, campanha_id, **body.model_dump(exclude_unset=True))
    return CampanhaOut(**row)


@router.delete("/campanhas/{campanha_id}", response_model=DeletedOut)
async def delete_campanha(
    campanha_id: UUID,
    auth=Depends(get_current_user_org),
    svc=Depends(get_portal_roi_service),
) -> DeletedOut:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    deleted = svc.delete_campanha(org_id, campanha_id)
    if not deleted:
        raise NotFoundError("lead_campanhas", str(campanha_id))
    return DeletedOut(deleted=True, id=campanha_id)


@router.get("/origens", response_model=OrigensOut)
async def get_origens(
    auth=Depends(get_current_user_org),
    svc=Depends(get_portal_roi_service),
) -> OrigensOut:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return OrigensOut(origens=svc.list_origens(org_id))


__all__ = ["router"]
