"""Platform grants API (Julia-line CONTRACT D1-D4): a NoctusAI platform admin wires an agent to a product for an org.

``GET    /api/studio/plataforma/grants``              list every grant (newest first)
``GET    /api/studio/plataforma/grants/opcoes``       the pickers: grantable products (server registry) + orgs (core)
``POST   /api/studio/plataforma/grants``              create = mint + DELIVER ``{agent_key, product, org_id, expira_em_dias?}``
``POST   /api/studio/plataforma/grants/{id}/rotate``  overlapping rotation (deliver the new pair, then revoke the old)
``DELETE /api/studio/plataforma/grants/{id}``         revoke both tokens + best-effort product DELETE (idempotent, 204)

``require_platform_admin``: 401 unauthenticated, 403 ``platform_admin_required`` for anyone else (an org owner/admin,
a product token and the platform content token included). NO response ever carries a secret: the credential is
delivered to the product over the one-shot call and exists nowhere else. A failed attempt answers 502 with a code
(``mint_failed`` / ``tools_store_failed`` / ``delivery_failed``), has revoked every token it minted, and leaves the
grant ``falhou`` with ``last_error`` (an error class and stage, no secrets). A second live grant for the same
(org, agent, product) is 409 ``grant_exists``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field

from app.channels.token_audit import TokenAudit
from app.dependencies import (
    get_grant_delivery_dep,
    get_grant_store_dep,
    get_grant_token_admin_dep,
    get_grant_tools_store_factory_dep,
    get_org_directory_dep,
    get_token_audit_dep,
    require_platform_admin,
)
from app.grants.orgs import ORG_LIST_MAX, OrgDirectory
from app.grants.registry import list_grant_products
from app.grants.service import GrantError, GrantService
from app.grants.store import Grant, GrantStore
from app.routers.studio_agents_router import actor_id, get_studio_definition_store_dep, http_error
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.grants import GrantDelivery
from noctusai_lib.api.auth.session import AuthContext, ProductTokenAdmin

router = APIRouter(tags=["plataforma-grants"])

_BASE = "/api/studio/plataforma/grants"
_CHAVE = r"^[a-z0-9]+([-_][a-z0-9]+)*$"


class GrantCreateRequest(StrictHttpModel):
    agent_key: str = Field(..., pattern=_CHAVE, max_length=64)
    product: str = Field(..., max_length=64)
    org_id: UUID
    #: ``None`` (the default) = the grant never expires; revocation and ``last_used_at`` still apply.
    expira_em_dias: int | None = Field(default=None, ge=1, le=3650)


class GrantOut(BaseModel):
    id: UUID
    org_id: UUID
    org_nome: str | None = None
    agent_id: UUID
    agent_key: str
    product: str
    status: str  # pendente | ativo | revogado | falhou
    channel_token_id: UUID | None = None
    #: The channel token's stored prefix (``noc_ab12``): agents keeps only the hash, so this is the whole honest display.
    token_prefix: str | None = None
    product_token_id: UUID | None = None
    expires_at: datetime | None = None
    created_by: UUID | None = None
    created_at: datetime | None = None
    revoked_by: UUID | None = None
    revoked_at: datetime | None = None
    last_delivered_at: datetime | None = None
    last_error: str | None = None


class GrantListOut(BaseModel):
    items: list[GrantOut]
    total: int


class ProdutoOut(BaseModel):
    slug: str
    label: str
    agent_keys: list[str]


class OrgOut(BaseModel):
    id: UUID
    nome: str
    slug: str | None = None


class GrantOpcoesOut(BaseModel):
    produtos: list[ProdutoOut]
    orgs: list[OrgOut]


def _out(grant: Grant, org_nome: str | None = None, token_prefix: str | None = None) -> GrantOut:
    return GrantOut(org_nome=org_nome, token_prefix=token_prefix, **grant.__dict__)


def _prefix_of(service: GrantService, grant: Grant) -> str | None:
    return service.channel_prefixes([grant]).get(grant.channel_token_id) if grant.channel_token_id else None


def get_grant_service_dep(
    grants: GrantStore = Depends(get_grant_store_dep),
    orgs: OrgDirectory = Depends(get_org_directory_dep),
    token_admin: ProductTokenAdmin = Depends(get_grant_token_admin_dep),
    delivery: GrantDelivery = Depends(get_grant_delivery_dep),
    tools_store_factory=Depends(get_grant_tools_store_factory_dep),
    studio_store=Depends(get_studio_definition_store_dep),
    audit: TokenAudit = Depends(get_token_audit_dep),
) -> GrantService:
    return GrantService(
        grants=grants, orgs=orgs, token_admin=token_admin, delivery=delivery,
        tools_store_factory=tools_store_factory, studio_store=studio_store, audit=audit,
    )


def _http(exc: GrantError):
    return http_error(exc.status, exc.code, exc.message)


@router.get(_BASE, response_model=GrantListOut)
def list_grants(
    ctx: AuthContext = Depends(require_platform_admin),
    service: GrantService = Depends(get_grant_service_dep),
) -> GrantListOut:
    rows = service.list()
    prefixes = service.channel_prefixes([g for g, _ in rows])
    items = [_out(g, nome, prefixes.get(g.channel_token_id)) for g, nome in rows]
    return GrantListOut(items=items, total=len(items))


@router.get(f"{_BASE}/opcoes", response_model=GrantOpcoesOut)
def grant_options(
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=ORG_LIST_MAX),
    ctx: AuthContext = Depends(require_platform_admin),
    orgs: OrgDirectory = Depends(get_org_directory_dep),
) -> GrantOpcoesOut:
    """The pickers. Products and their grantable agent keys come from the server registry; orgs from core, searched
    by name (``q``) and capped at ``limit``."""
    return GrantOpcoesOut(
        produtos=[ProdutoOut(slug=p.slug, label=p.label, agent_keys=list(p.agent_keys)) for p in list_grant_products()],
        orgs=[OrgOut(id=o.id, nome=o.nome, slug=o.slug) for o in orgs.search(q, limit=limit)],
    )


@router.post(_BASE, response_model=GrantOut, status_code=status.HTTP_201_CREATED)
def create_grant(
    payload: GrantCreateRequest,
    response: Response,
    ctx: AuthContext = Depends(require_platform_admin),
    service: GrantService = Depends(get_grant_service_dep),
) -> GrantOut:
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=payload.expira_em_dias) if payload.expira_em_dias else None
    )
    try:
        grant = service.create(
            agent_key=payload.agent_key, product=payload.product, org_id=payload.org_id,
            actor=actor_id(ctx), expires_at=expires_at,
        )
    except GrantError as exc:
        raise _http(exc) from exc
    response.headers["Cache-Control"] = "no-store"
    return _out(grant, service.org_name(grant.org_id), _prefix_of(service, grant))


@router.post(f"{_BASE}/{{grant_id}}/rotate", response_model=GrantOut)
def rotate_grant(
    grant_id: UUID,
    response: Response,
    ctx: AuthContext = Depends(require_platform_admin),
    service: GrantService = Depends(get_grant_service_dep),
) -> GrantOut:
    try:
        grant = service.rotate(grant_id, actor=actor_id(ctx))
    except GrantError as exc:
        raise _http(exc) from exc
    response.headers["Cache-Control"] = "no-store"
    return _out(grant, service.org_name(grant.org_id), _prefix_of(service, grant))


@router.delete(f"{_BASE}/{{grant_id}}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_grant(
    grant_id: UUID,
    ctx: AuthContext = Depends(require_platform_admin),
    service: GrantService = Depends(get_grant_service_dep),
) -> Response:
    try:
        service.revoke(grant_id, actor=actor_id(ctx))
    except GrantError as exc:
        raise _http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
