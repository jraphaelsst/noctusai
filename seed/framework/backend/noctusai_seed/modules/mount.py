"""Mounting modules: organs flatten through `mount_organs`; routers sit behind the per-org enablement guard;
`GET /api/modules` tells the FE which of this product's modules the caller's org has.

Guard order is the security contract: the guard DEPENDS on the host's auth dependency, so an unauthenticated call is
a strict 401 before enablement is looked at; an authenticated call into a disabled module is 403 `module_disabled`
(stable code); an enablement lookup outage is 503 (never "all on").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.api.access_tiers import access_tier
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.domain.module_enablement import (
    MODULE_DISABLED_CODE,
    ModuleEnablement,
    ModuleEnablementUnavailable,
)
from noctusai_seed.modules.spec import ModuleSpec, validate_modules
from noctusai_seed.organs import MountedOrgan, mount_organs

__all__ = ["ModuleMount", "mount_modules", "module_disabled"]


def module_disabled(module_key: str) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={"detail": "Este módulo não está habilitado para a sua organização.", "code": MODULE_DISABLED_CODE, "module": module_key},
    )


@dataclass(frozen=True)
class ModuleMount:
    #: `(router, guard dependencies)` pairs -- `app.include_router(router, dependencies=deps)`.
    guarded: tuple[tuple[APIRouter, tuple[Any, ...]], ...]
    #: routers mounted with no enablement guard (module `public_routers` + the `GET /api/modules` router).
    open_routers: tuple[APIRouter, ...]
    #: every organ of every module, for upload-size overrides (`mount_organs` merges + refuses conflicts).
    organs: tuple[MountedOrgan, ...]
    overrides: dict[str, int]


def _make_guard(spec: ModuleSpec, enablement: ModuleEnablement, auth_dependency: Callable[..., Any]):
    key = spec.enablement_key

    async def _guard(base: Any = Depends(auth_dependency)) -> None:
        org_id = base[2]
        try:
            ok = await run_blocking(enablement.is_enabled, org_id, key)
        except ModuleEnablementUnavailable:
            raise HTTPException(status_code=503, detail="Falha ao verificar os módulos da organização")
        if not ok:
            raise module_disabled(spec.key)

    return _guard


def _modules_router(specs: Sequence[ModuleSpec], enablement: ModuleEnablement, auth_dependency: Callable[..., Any]) -> APIRouter:
    router = APIRouter(prefix="/api/modules", tags=["Modules"])

    @router.get("")
    @access_tier("org", reason="auth dependency authenticates the caller; answers only the caller's own org enablement")
    async def my_modules(base: Any = Depends(auth_dependency)) -> dict[str, Any]:
        org_id = base[2]
        try:
            on = await run_blocking(enablement.enabled_modules, org_id)
        except ModuleEnablementUnavailable:
            raise HTTPException(status_code=503, detail="Falha ao consultar os módulos da organização")
        return {
            "modules": [
                {
                    "key": s.key,
                    "enablement_key": s.enablement_key,
                    "enabled": s.enablement_key in on,
                    "permissions": dict(s.permissions),
                }
                for s in specs
            ]
        }

    return router


def mount_modules(
    specs: Sequence[ModuleSpec], *, enablement: ModuleEnablement, auth_dependency: Callable[..., Any]
) -> ModuleMount:
    """`auth_dependency` yields `(user, token, org_id)` (the host's `get_current_user_org`)."""
    validate_modules(specs)
    missing = {s.enablement_key for s in specs} - enablement.known
    if missing:
        raise ValueError(f"enablement resolver does not know module keys {sorted(missing)}")
    guarded: list[tuple[APIRouter, tuple[Any, ...]]] = []
    open_routers: list[APIRouter] = []
    all_organs: list[MountedOrgan] = []
    for spec in specs:
        guard = Depends(_make_guard(spec, enablement, auth_dependency))
        routers, _ = mount_organs(list(spec.organs))
        guarded.extend((r, (guard,)) for r in routers)
        open_routers.extend(spec.public_routers)
        all_organs.extend(spec.organs)
    _, overrides = mount_organs(all_organs)
    open_routers.append(_modules_router(specs, enablement, auth_dependency))
    return ModuleMount(tuple(guarded), tuple(open_routers), tuple(all_organs), overrides)
