"""Staff-edit of a company's agent specs, authorised BY THE GRANT (owner decision 2026-11-05).

A grant is one (agent, product, org) with its own personal token. The same grant says who fills that org's agent
specs (``agent_product_grants.especificacoes_editor``, migration 064): ``plataforma`` = NoctusAI staff, from Studio,
without the company having any agents access (it stays internal and unlicensed).

``GET /api/studio/plataforma/agents/{key}/products/{product}/orgs``                     the picker: orgs with a LIVE grant
``GET /api/studio/plataforma/agents/{key}/products/{product}/orgs/{org_id}/specs``      that org's declared specs + values
``PUT /api/studio/plataforma/agents/{key}/products/{product}/orgs/{org_id}/specs``      ``{"valores": {...}}`` -- the SAME write path as the org PUT

Two conditions, both required: (1) the caller is a platform admin (``require_platform_admin``: 401 unauthenticated,
403 ``platform_admin_required``, the admin-MFA posture included) -- the login names the actor; (2) a grant row for
exactly (org_id, key, product) that is ``ativo`` and not expired, else 409 ``sem_concessao_ativa`` (``status`` says
why: ``inexistente`` / ``pendente`` / ``falhou`` / ``revogado`` / ``expirado``) and, when the grant's
``especificacoes_editor`` is not ``plataforma``, 409 ``editor_nao_plataforma``. ``definition_org_grants`` alone does not
count. Writes go through :func:`app.routers.studio_conteudo_router.aplicar_org_specs` (declared keys, per-type
validation, block/report mode, audit); the audit row lands in the TARGET org with the platform admin's real user id
and ``depois.origem = 'plataforma'`` + the grant + the changed keys. The social-wiring channel route stays read-only
(403 ``edicao_restrita_plataforma``).

``especificacoes_editor = 'org'`` is RESERVED (the org's own admins editing through the product): not built; switching
a grant to it makes this route refuse, it does not open another surface.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.dependencies import get_grant_store_dep, get_org_directory_dep, require_platform_admin
from app.grants.orgs import ORG_LIST_MAX, OrgDirectory
from app.grants.registry import get_grant_product
from app.grants.store import LIVE_STATUSES, Grant, GrantStore
from app.routers.studio_agents_router import get_studio_definition_store_dep, http_error
from app.routers.studio_conteudo_router import aplicar_org_specs, get_spec_validacao_dep, ler_org_specs
from app.schemas.studio_conteudo import OrgSpecsOut, OrgSpecsUpdateRequest
from app.stores.errors import NotFound
from app.studio.especificacoes_service import ConfigValidacao
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(tags=["plataforma-org-specs"], include_in_schema=False)

_BASE = "/api/studio/plataforma/agents/{key}/products/{product}/orgs"
EDITOR_PLATAFORMA = "plataforma"


class GrantOrgOut(BaseModel):
    org_id: UUID
    nome: str | None = None
    grant_id: UUID
    status: str  # pendente | ativo (a live row); `expirado` when ativo but past expires_at
    expires_at: datetime | None = None
    especificacoes_editor: str
    #: True only when the staff may edit NOW (ativo, not expired, editor = plataforma).
    editavel: bool


class GrantOrgsOut(BaseModel):
    agent_key: str
    product: str
    items: list[GrantOrgOut]


def _status_efetivo(g: Grant) -> str:
    return "expirado" if g.status == "ativo" and not g.is_live() else g.status


def _produto(key: str, product: str) -> None:
    spec = get_grant_product(product)
    if spec is None or key not in spec.agent_keys:
        raise http_error(404, "produto_desconhecido", "Este agente não é concedido a este produto.")


def _concessao(grants: GrantStore, key: str, product: str, org_id: UUID) -> Grant:
    """The grant that authorises a staff edit of ``org_id``'s specs: ativo, not expired, editor = plataforma."""
    _produto(key, product)
    rows = [g for g in grants.list(org_id=org_id) if g.agent_key == key and g.product == product]
    live = next((g for g in rows if g.is_live()), None)
    if live is None:
        status = _status_efetivo(rows[0]) if rows else "inexistente"  # newest first
        raise http_error(
            409, "sem_concessao_ativa", f"A empresa não tem uma concessão ativa deste agente neste produto ({status}).",
            status=status,
        )
    if live.especificacoes_editor != EDITOR_PLATAFORMA:
        raise http_error(
            409, "editor_nao_plataforma",
            "As especificações desta concessão não são editadas pela equipe NoctusAI.",
            especificacoes_editor=live.especificacoes_editor,
        )
    return live


def _alvo(store, grants: GrantStore, ctx: AuthContext, key: str, product: str, org_id: UUID) -> tuple[AuthContext, Grant]:
    """The ctx the shared org-spec service acts with: the caller (real ``user_id``) re-pointed at the TARGET org, whose
    instance the grant names."""
    grant = _concessao(grants, key, product, org_id)
    try:
        instancia = store.get_agent(org_id, key)
    except NotFound as exc:
        raise http_error(409, "org_sem_instancia", "A concessão existe, mas a empresa não tem a instância do agente.") from exc
    if instancia.id != grant.agent_id:
        raise http_error(409, "grant_agente_divergente", "A concessão aponta para outra instância do agente.")
    return ctx._replace(org_id=org_id), grant


@router.get(_BASE, response_model=GrantOrgsOut)
def list_orgs_com_concessao(
    key: str, product: str,
    ctx: AuthContext = Depends(require_platform_admin),
    grants: GrantStore = Depends(get_grant_store_dep),
    orgs: OrgDirectory = Depends(get_org_directory_dep),
) -> GrantOrgsOut:
    """The picker: every org with a LIVE grant (``pendente`` / ``ativo``) of ``key`` to ``product``, by name, each with its
    status and whether the staff may edit it now."""
    _produto(key, product)
    live = [g for g in grants.list() if g.agent_key == key and g.product == product and g.status in LIVE_STATUSES]
    nomes = {o.id: o.nome for o in orgs.search(None, limit=ORG_LIST_MAX)}
    items = [
        GrantOrgOut(
            org_id=g.org_id, nome=nomes.get(g.org_id), grant_id=g.id, status=_status_efetivo(g), expires_at=g.expires_at,
            especificacoes_editor=g.especificacoes_editor,
            editavel=g.is_live() and g.especificacoes_editor == EDITOR_PLATAFORMA,
        )
        for g in live
    ]
    items.sort(key=lambda i: ((i.nome or "￿").lower(), str(i.org_id)))
    return GrantOrgsOut(agent_key=key, product=product, items=items)


@router.get(f"{_BASE}/{{org_id}}/specs", response_model=OrgSpecsOut)
def get_specs_da_org(
    key: str, product: str, org_id: UUID,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
    grants: GrantStore = Depends(get_grant_store_dep),
    config: ConfigValidacao = Depends(get_spec_validacao_dep),
) -> OrgSpecsOut:
    alvo, _ = _alvo(store, grants, ctx, key, product, org_id)
    return ler_org_specs(store, alvo, key, config)


@router.put(f"{_BASE}/{{org_id}}/specs", response_model=OrgSpecsOut)
def put_specs_da_org(
    key: str, product: str, org_id: UUID, payload: OrgSpecsUpdateRequest,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
    grants: GrantStore = Depends(get_grant_store_dep),
    config: ConfigValidacao = Depends(get_spec_validacao_dep),
) -> OrgSpecsOut:
    """Fill the target org's specs. Same declared-keys rule, per-type validation (422 per field in block mode) and
    audit as the org route; ``updated_by`` and the audit actor are the platform admin."""
    alvo, grant = _alvo(store, grants, ctx, key, product, org_id)
    return aplicar_org_specs(
        store, alvo, key, payload.valores, config,
        origem={
            "origem": "plataforma", "produto": product, "grant_id": str(grant.id), "org_alvo": str(org_id),
            "ator_plataforma": str(ctx.user_id),
        },
    )
