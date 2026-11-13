"""``routines_router(...)`` -- mountable, org-admin-only HTTP surface for routines.

A factory (mirrors ``editorial_router``): auth, org membership/role and storage are injected.

Routes (under the caller's prefix; EVERY route needs an authenticated org ADMIN -- config
holds search/source params and the switches stop production work; non-admin member = 403):
    GET    ""                          routines + the master switch state
    POST   ""                          create {name, cron, mode?, config?}  (starts DISABLED)
    GET    "/master"                   {enabled}
    PUT    "/master"                   {enabled, reason}      -- flip the per-product master switch
    GET    "/events"                   ?routine_id=&kind=&limit=   the append-only log
    GET    "/report"                   ?days=                   the daily report numbers
    GET    "/{id}"                     one routine
    PATCH  "/{id}"                     edit {name?, cron?, config?, mode?, reason?}
    POST   "/{id}/enable"|"/disable"   {reason}  (enable also clears a kill)
    POST   "/{id}/kill"                {reason}  (never fires again until enabled)
    POST   "/{id}/trigger"             run now (a trigger-mode run => editorial drafts awaiting approval)
    POST   "/{id}/drafts/{item_id}/approve"   one-step approval
    POST   "/{id}/drafts/{item_id}/reject"    {reason}  (required)

Security: the org is the one the PRODUCT verified for the caller (``RoutinesContext.org_id``,
``None`` => 403); editorial grants are derived SERVER-SIDE (admin => editar + publicar), never
read from a body (bodies are ``StrictHttpModel`` => an extra field is a 422). Every flip needs a reason.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Mapping
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.domain.editorial.store import EditorialDenied, EditorialNotFound
from noctusai_lib.domain.routines.report import aggregate_events
from noctusai_lib.domain.routines.service import RoutineService
from noctusai_lib.domain.routines.store import RoutineStore
from noctusai_lib.domain.routines.types import (
    RoutineBlocked,
    RoutineConflict,
    RoutineInvalid,
    RoutineNotFound,
)
from noctusai_lib.domain.routines.workflow import ADMIN_GRANTS

_DENIAL_STATUS = {
    "actor_required": 401, "missing_grant": 403, "illegal_transition": 409,
    "motivo_required": 422, "content_required": 422, "unknown_action": 422,
}


@dataclass(frozen=True)
class RoutinesContext:
    """``org_id`` = the org the caller is a VERIFIED member of (None => 403); ``is_org_admin`` = the
    product's own org-admin check."""

    org_id: UUID | None
    user_id: UUID | None
    is_org_admin: bool = False


class RoutineCreate(StrictHttpModel):
    name: str = Field(..., min_length=1, max_length=120)
    cron: str = Field(..., min_length=9, max_length=120)
    mode: str = Field(default="trigger", max_length=20)
    config: dict[str, Any] = Field(default_factory=dict)


class RoutineEdit(StrictHttpModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    cron: str | None = Field(default=None, min_length=9, max_length=120)
    mode: str | None = Field(default=None, max_length=20)
    config: dict[str, Any] | None = None
    reason: str | None = Field(default=None, max_length=2000)


class ReasonBody(StrictHttpModel):
    reason: str = Field(..., min_length=3, max_length=2000)


class MasterBody(StrictHttpModel):
    enabled: bool
    reason: str = Field(..., min_length=3, max_length=2000)


def _jsonable(x: Any) -> Any:
    if isinstance(x, Enum):
        return x.value
    if isinstance(x, UUID):
        return str(x)
    if isinstance(x, datetime):
        return x.isoformat()
    if is_dataclass(x) and not isinstance(x, type):
        return {f.name: _jsonable(getattr(x, f.name)) for f in fields(x)}
    if isinstance(x, Mapping):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def routines_router(
    *,
    auth_dependency: Callable[..., Any],
    resolve_context: Callable[[Any], RoutinesContext],
    get_store: Callable[[], RoutineStore],
    get_service: Callable[[], RoutineService],
    success_response: Callable[[Any], Any],
    prefix: str = "",
    tags: list[str] | None = None,
):
    router = make_router(tier="org", guard=auth_dependency, prefix=prefix, tags=tags or ["routines"])

    def _ctx(auth: Any) -> RoutinesContext:
        ctx = resolve_context(auth)
        if ctx.user_id is None:
            raise HTTPException(401, detail={"detail": "Authentication required", "code": "actor_required"})
        if ctx.org_id is None:
            raise HTTPException(403, detail={"detail": "Not a member of this organization",
                                             "code": "org_membership_required"})
        if not ctx.is_org_admin:
            raise HTTPException(403, detail={"detail": "Organization admin required", "code": "admin_required"})
        return ctx

    def _err(e: Exception) -> HTTPException:
        if isinstance(e, (RoutineNotFound, EditorialNotFound)):
            return HTTPException(404, detail={"detail": str(e), "code": "not_found"})  # detail-safe: domain-authored
        if isinstance(e, RoutineConflict):
            return HTTPException(409, detail={"detail": str(e), "code": "already_exists"})  # detail-safe: domain-authored
        if isinstance(e, RoutineBlocked):
            return HTTPException(409, detail={"detail": str(e), "code": e.reason})  # detail-safe: domain-authored message
        if isinstance(e, RoutineInvalid):
            return HTTPException(422, detail={"detail": str(e), "code": "invalid"})  # detail-safe: domain-authored
        if isinstance(e, EditorialDenied):
            return HTTPException(_DENIAL_STATUS.get(e.code, 409), detail={"detail": e.detail or e.code, "code": e.code})  # detail-safe: domain-authored message
        raise e

    @router.get("")
    def listar(auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        store = get_store()
        return success_response({
            "routines": _jsonable(store.list_routines(ctx.org_id)),
            "master_enabled": store.master_enabled(ctx.org_id),
        })

    @router.post("", status_code=201)
    def criar(body: RoutineCreate, auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        try:
            r = get_store().create_routine(org_id=ctx.org_id, name=body.name, cron=body.cron, mode=body.mode,
                                           config=body.config, actor_id=ctx.user_id)
        except (RoutineConflict, RoutineInvalid) as e:
            raise _err(e)
        return success_response(_jsonable(r))

    @router.get("/master")
    def master(auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        return success_response({"enabled": get_store().master_enabled(ctx.org_id)})

    @router.put("/master")
    def set_master(body: MasterBody, auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        try:
            enabled = get_store().set_master(org_id=ctx.org_id, enabled=body.enabled, actor_id=ctx.user_id,
                                             reason=body.reason)
        except RoutineInvalid as e:
            raise _err(e)
        return success_response({"enabled": enabled})

    @router.get("/events")
    def eventos(routine_id: UUID | None = None, kind: str | None = None,
                limit: int = Query(100, ge=1, le=500), auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        evs = get_store().list_events(ctx.org_id, routine_id=routine_id,
                                      kinds=None if kind is None else [kind], limit=limit)
        return success_response({"events": _jsonable(evs)})

    @router.get("/report")
    def relatorio(days: int = Query(1, ge=1, le=31), auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        store = get_store()
        since = datetime.now(timezone.utc) - timedelta(days=days)
        agg = aggregate_events(store.list_routines(ctx.org_id), store.list_events(ctx.org_id, since=since))
        return success_response({**agg, "master_enabled": store.master_enabled(ctx.org_id), "days": days})

    @router.get("/{routine_id}")
    def detalhe(routine_id: UUID, auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        try:
            return success_response(_jsonable(get_store().get_routine(ctx.org_id, routine_id)))
        except RoutineNotFound as e:
            raise _err(e)

    @router.patch("/{routine_id}")
    def editar(routine_id: UUID, body: RoutineEdit, auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        try:
            r = get_store().update_routine(org_id=ctx.org_id, routine_id=routine_id, actor_id=ctx.user_id,
                                           name=body.name, cron=body.cron, config=body.config, mode=body.mode,
                                           reason=body.reason)
        except (RoutineNotFound, RoutineConflict, RoutineInvalid) as e:
            raise _err(e)
        return success_response(_jsonable(r))

    def _flip(routine_id: UUID, body: ReasonBody, auth: Any, enabled: bool):
        ctx = _ctx(auth)
        try:
            r = get_store().set_enabled(org_id=ctx.org_id, routine_id=routine_id, enabled=enabled,
                                        actor_id=ctx.user_id, reason=body.reason)
        except (RoutineNotFound, RoutineInvalid) as e:
            raise _err(e)
        return success_response(_jsonable(r))

    @router.post("/{routine_id}/enable")
    def ligar(routine_id: UUID, body: ReasonBody, auth=Depends(auth_dependency)):
        return _flip(routine_id, body, auth, True)

    @router.post("/{routine_id}/disable")
    def desligar(routine_id: UUID, body: ReasonBody, auth=Depends(auth_dependency)):
        return _flip(routine_id, body, auth, False)

    @router.post("/{routine_id}/kill")
    def matar(routine_id: UUID, body: ReasonBody, auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        try:
            r = get_store().kill(org_id=ctx.org_id, routine_id=routine_id, actor_id=ctx.user_id, reason=body.reason)
        except (RoutineNotFound, RoutineInvalid) as e:
            raise _err(e)
        return success_response(_jsonable(r))

    @router.post("/{routine_id}/trigger")
    async def disparar(routine_id: UUID, auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        try:
            res = await get_service().run(ctx.org_id, routine_id, scheduled=False, actor_id=ctx.user_id)
        except (RoutineNotFound, RoutineBlocked, RoutineInvalid) as e:
            raise _err(e)
        return success_response(_jsonable(res))

    @router.post("/{routine_id}/drafts/{item_id}/approve")
    def aprovar(routine_id: UUID, item_id: UUID, auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        try:
            res = get_service().approve(ctx.org_id, routine_id, item_id, actor_id=ctx.user_id, grants=ADMIN_GRANTS)
        except (RoutineNotFound, EditorialNotFound, EditorialDenied) as e:
            raise _err(e)
        return success_response(_jsonable(res))

    @router.post("/{routine_id}/drafts/{item_id}/reject")
    def rejeitar(routine_id: UUID, item_id: UUID, body: ReasonBody, auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        try:
            res = get_service().reject(ctx.org_id, routine_id, item_id, actor_id=ctx.user_id,
                                       grants=ADMIN_GRANTS, reason=body.reason)
        except (RoutineNotFound, EditorialNotFound, EditorialDenied) as e:
            raise _err(e)
        return success_response(_jsonable(res))

    return router


__all__ = ["RoutinesContext", "routines_router"]
