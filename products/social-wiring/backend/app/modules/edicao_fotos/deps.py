"""DI seams + authorization for `/api/edicao-fotos`.

Every route resolves, in this order:

1. `get_actor` — `get_current_user_org` (the product's trusted auth dep: a
   missing/invalid credential is a strict 401 HERE, before anything else
   runs) + the trusted-DB role read (`get_role_resolver`). Roles NEVER come
   from SSO metadata (contract §1).
2. A role guard (`require_member` / `require_org_admin` /
   `require_platform_admin` / `require_pool_manager`) — 403 with a named code.
3. The engine ports / grant repository / Vista source — 503 with a named
   cause when this process cannot build them.

Tests replace the seams with `app.dependency_overrides[...]`; nothing here is
monkeypatched (`KB § PATTERNS/backend/di-test-seam.md`).

🔴 The engine runs on a SERVICE-ROLE client (RLS bypass), so org scoping is
enforced HERE: `load_visible_batch` answers 404 for a batch of another org, or
— for a corretor — a batch someone else created (the same rows RLS
`fotos_lote_visivel` would withhold). R1 keeps platform admins inside their own
org as well; cross-org reads belong to the platform dashboard slice.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Depends

from noctusai_lib.api.auth.platform import resolve_platform_admin_role
from noctusai_lib.api.auth.session.scopes import resolve_org_role
from noctusai_lib.domain.permissions import PermissionGrantRepository
from noctusai_lib.domain.photo_editing import Actor, Batch, PhotoEditingPorts
from noctusai_lib.domain.photo_editing.types import (
    AGENCY_ADMIN_ROLES,
    CORRETOR_ROLES,
    PHOTO_CURATOR_PERMISSION,
    OrgRule,
)

from app.dependencies import coerce_org_uuid, get_current_user_org, get_settings
from app.modules.edicao_fotos.errors import api_error
from app.modules.edicao_fotos.services import ports as ports_service
from app.modules.edicao_fotos.services.notificacoes_preferencias import (
    NotificationPreferencesRepository,
)
from app.modules.edicao_fotos.services.vista_fotos import (
    RealVistaPhotoSource,
    VistaPhotoSource,
)


@dataclass(frozen=True)
class RoleInfo:
    org_role: str | None
    is_platform_admin: bool


RoleResolver = Callable[[str], RoleInfo]


def _trusted_roles(user_id: str) -> RoleInfo:
    from app.dependencies import get_core_client

    core = get_core_client()
    return RoleInfo(
        org_role=resolve_org_role(core, user_id),
        is_platform_admin=resolve_platform_admin_role(core, user_id) == "admin",
    )


def get_role_resolver() -> RoleResolver:
    """Seam: `user_id -> RoleInfo`, read from `public.noctus_users`."""
    return _trusted_roles


def get_actor(
    auth: tuple = Depends(get_current_user_org),
    resolve_roles: RoleResolver = Depends(get_role_resolver),
) -> Actor:
    user, _token, raw_org = auth
    user_id = str(getattr(user, "id", "") or "")
    if not user_id:
        # A product-token caller has no user; this surface is user-only.
        raise api_error(403, "usuario_obrigatorio", "Esta área exige um usuário autenticado.")
    roles = resolve_roles(user_id)
    return Actor(
        user_id=user_id,
        org_id=str(coerce_org_uuid(raw_org)),
        org_role=roles.org_role,
        is_platform_admin=roles.is_platform_admin,
    )


def is_member(actor: Actor) -> bool:
    return actor.is_platform_admin or actor.org_role in (AGENCY_ADMIN_ROLES | CORRETOR_ROLES)


def can_see_verdict(actor: Actor) -> bool:
    """Contract §1: platform admins + agency admins; corretores NEVER."""
    return actor.is_platform_admin or actor.is_agency_admin


def require_member(actor: Actor = Depends(get_actor)) -> Actor:
    if not is_member(actor):
        raise api_error(
            403, "sem_acesso_edicao_fotos", "Seu papel na organização não dá acesso à Edição de Fotos."
        )
    return actor


def require_org_admin(actor: Actor = Depends(get_actor)) -> Actor:
    if not (actor.is_platform_admin or actor.is_agency_admin):
        raise api_error(
            403, "restrito_admin_organizacao", "Restrito a administradores da organização."
        )
    return actor


def require_platform_admin(actor: Actor = Depends(get_actor)) -> Actor:
    if not actor.is_platform_admin:
        raise api_error(
            403, "restrito_admin_plataforma", "Restrito a administradores da plataforma NoctusAI."
        )
    return actor


def get_grant_repository() -> PermissionGrantRepository:
    try:
        return ports_service.get_grant_repository()
    except ports_service.EdicaoFotosUnavailable as exc:
        raise api_error(503, exc.code, str(exc)) from exc


def get_preferences_repository() -> NotificationPreferencesRepository:
    try:
        return ports_service.get_preferences_repository()
    except ports_service.EdicaoFotosUnavailable as exc:
        raise api_error(503, exc.code, str(exc)) from exc


async def require_pool_manager(
    actor: Actor = Depends(get_actor),
    grants: PermissionGrantRepository = Depends(get_grant_repository),
) -> Actor:
    """Contract §1: reference pool CRUD + guide lifecycle — platform admin
    or a `photo_curator` grant holder (Core `user_permission_grants`),
    whatever their org role. Platform scope: never an agency admin."""
    if actor.is_platform_admin or await grants.has_permission(
        user_id=actor.user_id, permission=PHOTO_CURATOR_PERMISSION
    ):
        return actor
    raise api_error(
        403,
        "restrito_curadoria",
        "Restrito a administradores da plataforma e curadores de fotos.",
    )


def get_edicao_ports(cfg: Any = Depends(get_settings)) -> PhotoEditingPorts:
    try:
        return ports_service.get_ports(cfg)
    except ports_service.EdicaoFotosUnavailable as exc:
        raise api_error(503, exc.code, str(exc)) from exc


def get_painel_client() -> Any:
    """FastAPI dependency — the `social_wiring`-scoped admin (service-role)
    client used ONLY by the dashboard RPC (`fotos_painel`, migration 133,
    contract §8 `GET /painel`). Reuses the platform's own formalized
    schema-scoped-client cache (`app.dependencies.get_scoped_admin_client`)
    rather than re-deriving a fourth local copy of that cache — see that
    function's docstring for the `MockSupabaseClient.schema()` data-loss
    defect it fixes."""
    from app.dependencies import get_scoped_admin_client

    return get_scoped_admin_client("social_wiring")


def get_vista_photo_source(cfg: Any = Depends(get_settings)) -> VistaPhotoSource:
    """The product's EXISTING Vista credentials (`VISTA_API_KEY` →
    `crm_api_key`). Missing → 503, never a fallback."""
    from noctusai_lib.integrations.vista import VistaNotConfigured, VistaRESTAdapter

    try:
        adapter = VistaRESTAdapter(base_url=cfg.crm_base_url, api_key=cfg.crm_api_key)
    except VistaNotConfigured as exc:
        raise api_error(503, "vista_nao_configurado", f"Vista não configurado: {exc}") from exc
    return RealVistaPhotoSource(adapter)


def batch_visible_to(actor: Actor, batch: Batch) -> bool:
    if str(batch.org_id) != actor.org_id:
        return False
    return actor.is_platform_admin or actor.is_agency_admin or str(batch.criado_por) == actor.user_id


async def load_visible_batch(ports: PhotoEditingPorts, actor: Actor, lote_id: str) -> Batch:
    batch = await ports.repo.get_batch(lote_id)
    if batch is None or not batch_visible_to(actor, batch):
        # 404, not 403: an invisible batch does not exist for this caller.
        raise api_error(404, "lote_nao_encontrado", "Lote não encontrado.")
    return batch


async def load_visible_rule(ports: PhotoEditingPorts, actor: Actor, regra_id: str) -> OrgRule:
    """W7 (`/regras`) — same "R1 keeps every caller inside their own org"
    rule as `load_visible_batch`, applied to platform admins too: a rule
    from another org 404s rather than 403ing, so its existence never
    leaks. `learning.decide_rule`'s own authority check (agency admin vs.
    platform-admin override) runs AFTER this and stays in charge of
    WITHIN-org decisions."""
    rule = await ports.repo.get_rule(regra_id)
    if rule is None or rule.org_id != actor.org_id:
        raise api_error(404, "regra_nao_encontrada", "Regra não encontrada.")
    return rule


__all__ = [
    "RoleInfo",
    "RoleResolver",
    "batch_visible_to",
    "can_see_verdict",
    "get_actor",
    "get_edicao_ports",
    "get_grant_repository",
    "get_painel_client",
    "get_preferences_repository",
    "get_role_resolver",
    "get_vista_photo_source",
    "is_member",
    "load_visible_batch",
    "load_visible_rule",
    "require_member",
    "require_org_admin",
    "require_platform_admin",
    "require_pool_manager",
]
