"""Planos (paid tiers) router — contract §Planos, plus module 2's
gateway-refs sub-resource (§Gateway refs) and the PUBLIC tier listing
(amendment A17).

Auth: `Depends(get_current_user_org)` on every route (401 boundary)
EXCEPT `GET /publicos`, which is genuinely unauthenticated (amendment
A17 — org resolved via `resolve_public_org_id()`, same convention as
`aplicacoes_router.py`'s public routes). Reads allow both community
roles (`admin` + `moderador`) — no extra gate beyond authentication.
Writes are `admin`-only via `require_admin`.

🔴 Route-ordering note: `GET /publicos` is registered BEFORE
`GET /{plano_id}` — both are single-segment paths under this router's
prefix, and FastAPI/Starlette matches in REGISTRATION order. Reversing
this order would make `GET /api/planos/publicos` fall through to
`get_plano(plano_id="publicos")` (401, since that route requires auth)
instead of ever reaching the public handler.

Deliberately NO ``from __future__ import annotations`` — same
`@limiter.limit(...)` + Pydantic-response-model interaction documented
at the top of `app/routers/aplicacoes_router.py`: combined with a
postponed annotation, slowapi's wrapper resolves this function's type
hints (including its `-> PlanoPublicoListResponse` return annotation)
against ITS OWN module globals rather than this module's, and FastAPI
fails to build the route. Python 3.11 (this repo's runtime) evaluates
`bool | None` / `list[...]` natively, so nothing below needs the
postponed-evaluation behavior anyway.
"""
import logging

from fastapi import APIRouter, Depends, Query, Request, status

from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    http_error,
    get_admin_client,
    get_community_role,
    get_current_user_org,
    get_user_client,
    require_admin,
    resolve_public_org_id,
)
from app.rate_limit import limiter
from app.schemas.pagamentos import (
    GatewayRef,
    GatewayRefListResponse,
    GatewayRefUpsert,
    PlanoPublicoListResponse,
)
from app.schemas.planos import (
    Plano,
    PlanoCreate,
    PlanoListResponse,
    PlanoUpdate,
)
from app.services.gateway_refs_service import GatewayRefsService, GatewayRefsServiceError
from app.services.planos_publicos_service import PlanosPublicosService
from app.services.planos_service import PlanosService, PlanosServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/planos", tags=["planos"])

_VALID_GATEWAYS = ("stripe", "asaas")


@router.get("", response_model=PlanoListResponse)
async def list_planos(
    ativo: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> PlanoListResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = PlanosService(client, org_id=org_id)
    result = await service.list(ativo=ativo, page=page, page_size=page_size)
    return PlanoListResponse(**result)


# ── PUBLIC (amendment A17) ────────────────────────────────────────────
#
# Registered here, BEFORE `GET /{plano_id}` below — see the module
# docstring's route-ordering note.


@router.get("/publicos", response_model=PlanoPublicoListResponse)
@limiter.limit(settings.checkout_rate_limit)
async def list_planos_publicos(request: Request) -> PlanoPublicoListResponse:
    org_id = resolve_public_org_id()
    client = get_admin_client()
    service = PlanosPublicosService(client, org_id=org_id)
    result = await service.list()
    return PlanoPublicoListResponse(**result)


@router.post("", response_model=Plano, status_code=status.HTTP_201_CREATED)
async def create_plano(
    payload: PlanoCreate,
    auth: tuple = Depends(get_current_user_org),
) -> Plano:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="criar planos")
    client = get_user_client(token)
    service = PlanosService(client, org_id=org_id)
    body = payload.model_dump()
    try:
        row = await service.create(payload=body)
    except PlanosServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return Plano(**row)


@router.get("/{plano_id}", response_model=Plano)
async def get_plano(
    plano_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> Plano:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = PlanosService(client, org_id=org_id)
    row = await service.get(plano_id=plano_id)
    if not row:
        raise http_error(404, "Plano não encontrado.")
    return Plano(**row)


@router.patch("/{plano_id}", response_model=Plano)
async def update_plano(
    plano_id: str,
    payload: PlanoUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> Plano:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="editar planos")
    client = get_user_client(token)
    service = PlanosService(client, org_id=org_id)
    data = payload.model_dump(exclude_none=True)
    try:
        row = await service.update(plano_id=plano_id, payload=data)
    except PlanosServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    if not row:
        raise http_error(404, "Plano não encontrado.")
    return Plano(**row)


@router.delete("/{plano_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plano(
    plano_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> None:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="excluir planos")
    client = get_user_client(token)
    service = PlanosService(client, org_id=org_id)
    ok = await service.soft_delete(plano_id=plano_id)
    if not ok:
        raise http_error(404, "Plano não encontrado.")
    return None


# ── Gateway refs (admin) — contract §Gateway refs ─────────────────────
#
# `/{plano_id}/gateway-refs...` paths carry an EXTRA segment beyond the
# bare `/{plano_id}` route above, so there is no route-ordering hazard
# here (unlike `/publicos`).


@router.get("/{plano_id}/gateway-refs", response_model=GatewayRefListResponse)
async def list_gateway_refs(
    plano_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> GatewayRefListResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = GatewayRefsService(client, org_id=org_id)
    try:
        result = await service.list(plano_id=plano_id)
    except GatewayRefsServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return GatewayRefListResponse(**result)


@router.put("/{plano_id}/gateway-refs/{gateway}", response_model=GatewayRef)
async def upsert_gateway_ref(
    plano_id: str,
    gateway: str,
    payload: GatewayRefUpsert,
    auth: tuple = Depends(get_current_user_org),
) -> GatewayRef:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="configurar referências de gateway")
    if gateway not in _VALID_GATEWAYS:
        raise http_error(404, "Gateway não suportado.")
    client = get_user_client(token)
    service = GatewayRefsService(client, org_id=org_id)
    try:
        row = await service.upsert(
            plano_id=plano_id, gateway=gateway, ref_externo=payload.ref_externo,
        )
    except GatewayRefsServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return GatewayRef(**row)


@router.delete("/{plano_id}/gateway-refs/{gateway}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gateway_ref(
    plano_id: str,
    gateway: str,
    auth: tuple = Depends(get_current_user_org),
) -> None:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="remover referências de gateway")
    if gateway not in _VALID_GATEWAYS:
        raise http_error(404, "Gateway não suportado.")
    client = get_user_client(token)
    service = GatewayRefsService(client, org_id=org_id)
    ok = await service.delete(plano_id=plano_id, gateway=gateway)
    if not ok:
        raise http_error(404, "Referência de gateway não encontrada.")
    return None
