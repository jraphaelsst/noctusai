"""Platform-admin write API for per-org module enablement (the core admin dashboard consumes it).

    GET /api/platform/org-modules/{org_id}                 -> every canonical module key with `enabled`
    PUT /api/platform/org-modules/{org_id}/{module_key}    {enabled: bool} -> the updated item

Access tier `platform`: gated by `require_platform_admin` (strict 401 from the product's `get_auth_context`, 403
`platform_admin_required` for anyone whose `noctus_users.role` is not `admin` -- an org owner/admin never qualifies).
The org must exist (404 `org_not_found`); the key must be a canonical module-group key (422 otherwise).
The core admin PAGE that calls this is a follow-up; this module only ships the API.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.api.access_tiers import access_tier
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.platform import require_platform_admin
from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.api.schemas import StrictHttpModel

from .keys import MODULE_GROUP_KEYS
from .store import ModuleEnablement, ModuleEnablementUnavailable

logger = logging.getLogger(__name__)

__all__ = ["OrgModuleItem", "OrgModulesOut", "OrgModuleUpdate", "create_org_modules_admin_router"]


class OrgModuleItem(StrictHttpModel):
    key: str
    enabled: bool


class OrgModulesOut(StrictHttpModel):
    org_id: str
    modules: list[OrgModuleItem]


class OrgModuleUpdate(StrictHttpModel):
    enabled: bool


def create_org_modules_admin_router(
    *,
    get_auth_context: Callable[..., Awaitable[AuthContext]],
    get_core_client: Callable[[], Any],
    enablement: ModuleEnablement,
    prefix: str = "/api/platform/org-modules",
) -> APIRouter:
    """`enablement` must be built over the canonical keys (`ModuleEnablement(store, MODULE_GROUP_KEYS)`)."""
    if not set(MODULE_GROUP_KEYS) <= enablement.known:
        raise ValueError("the admin router needs a ModuleEnablement over every canonical module-group key")
    router = APIRouter(prefix=prefix, tags=["Platform · Org modules"], include_in_schema=False)
    platform_admin = require_platform_admin(get_auth_context=get_auth_context, get_core_client=get_core_client)

    def _org_uuid(org_id: str) -> str:
        try:
            return str(UUID(org_id))
        except ValueError:
            raise HTTPException(status_code=422, detail={"detail": "org_id inválido", "code": "org_id_invalid"})

    async def _require_org(org_id: str) -> None:
        res = await run_blocking(
            lambda: get_core_client().table("organizations").select("id").eq("id", org_id).limit(1).execute()
        )
        if not (res.data or []):
            raise HTTPException(status_code=404, detail={"detail": "Organização não encontrada", "code": "org_not_found"})

    async def _enabled(org_id: str) -> frozenset[str]:
        try:
            return await run_blocking(enablement.enabled_modules, org_id)
        except ModuleEnablementUnavailable:
            raise HTTPException(status_code=503, detail="Falha ao consultar os módulos da organização")

    @router.get("/{org_id}", response_model=OrgModulesOut)
    @access_tier("platform", reason="require_platform_admin gate; entitlements are NoctusAI commercial config")
    async def list_org_modules(org_id: str, _ctx: AuthContext = Depends(platform_admin)) -> OrgModulesOut:
        oid = _org_uuid(org_id)
        await _require_org(oid)
        on = await _enabled(oid)
        return OrgModulesOut(org_id=oid, modules=[OrgModuleItem(key=k, enabled=k in on) for k in MODULE_GROUP_KEYS])

    @router.put("/{org_id}/{module_key}", response_model=OrgModuleItem)
    @access_tier("platform", reason="require_platform_admin gate; entitlements are NoctusAI commercial config")
    async def set_org_module(
        org_id: str, module_key: str, body: OrgModuleUpdate, ctx: AuthContext = Depends(platform_admin)
    ) -> OrgModuleItem:
        oid = _org_uuid(org_id)
        if module_key not in MODULE_GROUP_KEYS:
            raise HTTPException(
                status_code=422,
                detail={"detail": f"módulo desconhecido: {module_key!r}", "code": "module_key_unknown"},
            )
        await _require_org(oid)
        try:
            await run_blocking(enablement.set_enabled, oid, module_key, body.enabled, updated_by=ctx.user_id)
        except ModuleEnablementUnavailable:
            raise HTTPException(status_code=503, detail="Falha ao gravar o módulo da organização")
        logger.info("org_module_set org=%s module=%s enabled=%s by=%s", oid, module_key, body.enabled, ctx.user_id)
        return OrgModuleItem(key=module_key, enabled=body.enabled)

    return router
