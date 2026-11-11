"""Activities HTTP surface -- `make_activities_router(cfg, auth_dependency, admin_dependency, ...)` at `/api/activities`.

Org STAFF may use every activity route (a task is operational: create, complete, reassign, reschedule, cancel);
the market's activity TYPES are settings, so their writes additionally require `admin_dependency`. Unauthenticated is a
strict 401 (it lives in the host's `auth_dependency`); every query is filtered by the caller's org, so a foreign id is a 404.

    GET    /types?active=            POST /types (admin)          PATCH /types/{slug} (admin)
    GET    /?entity_kind=&entity_id=&assignee_id=&status=&type_slug=&kind=&overdue=&due_from=&due_to=&page=&page_size=
    GET    /mine                     the caller's own (same filters minus assignee_id)
    POST   /                         GET /{id}      GET /{id}/events      PATCH /{id}
    POST   /{id}/complete | /reopen | /reassign | /reschedule | /cancel

Envelopes `{"data": ...}` / `{"data": [...], "pagination": {...}}`. Handlers are plain `def` (blocking PostgREST IO runs in
the threadpool). 🔴 NEVER `get_admin_client().schema(...)` in here: `get_db` already returns the schema-scoped client.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from noctusai_lib.primitives.responses import paginated_response, success_response

from . import service as svc
from .config import ActivitiesConfig, ActivitiesContext
from .schemas import (
    ActivityBody,
    ActivityPatch,
    CompleteBody,
    ReassignBody,
    RescheduleBody,
    TypeBody,
    TypePatch,
)

MAX_PAGE = 200


def make_activities_router(
    cfg: ActivitiesConfig,
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    *,
    resolve_context: Callable[[Any, Any], ActivitiesContext],
    get_db: Callable[..., Any],
    prefix: str = "/api/activities",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    """Build the activities router.

    Args:
        auth_dependency: the product's license-gated `get_current_user_org` (401 / 403 live there).
        admin_dependency: the org-admin gate; raises 403 for staff (used for the activity TYPES writes only).
        resolve_context: `(auth_value, db) -> ActivitiesContext(db, org_id, user_id, is_admin, is_member)`.
        get_db: FastAPI dependency returning the schema-scoped client.
    """
    router = APIRouter(prefix=prefix, tags=tags or ["activities"])

    def ctx_dep(auth=Depends(auth_dependency), db=Depends(get_db)) -> ActivitiesContext:
        return resolve_context(auth, db)

    def scope(ctx: ActivitiesContext) -> svc.Scope:
        return svc.Scope(ctx.db, cfg, str(ctx.org_id))

    def uid(ctx: ActivitiesContext) -> Optional[str]:
        return str(ctx.user_id) if ctx.user_id else None

    admin = Depends(admin_dependency)

    # ── types ──
    @router.get("/types", name="activities_list_types")
    def list_types_route(active: Optional[bool] = Query(None), ctx: ActivitiesContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.list_types(scope(ctx), active=active))

    @router.post("/types", status_code=201, name="activities_create_type")
    def create_type_route(body: TypeBody, _a=admin, ctx: ActivitiesContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.create_type(scope(ctx), body.model_dump()))

    @router.patch("/types/{slug}", name="activities_update_type")
    def update_type_route(slug: str, body: TypePatch, _a=admin, ctx: ActivitiesContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.update_type(scope(ctx), slug, body.model_dump(exclude_unset=True)))

    # ── lists ──
    def _list(
        ctx: ActivitiesContext, assignee_id: Optional[UUID], entity_kind, entity_id, status, type_slug, kind, overdue, due_from, due_to, page, page_size
    ) -> dict:
        rows, total, pg, size = svc.list_activities(
            scope(ctx), entity_kind=entity_kind, entity_id=entity_id, assignee_id=assignee_id, status=status, type_slug=type_slug,
            kind=kind, overdue=overdue, due_from=due_from, due_to=due_to, page=page, page_size=page_size,
        )
        return paginated_response(rows, total, pg, size)

    @router.get("/mine", name="activities_mine")
    def mine_route(
        entity_kind: Optional[str] = Query(None, max_length=60),
        entity_id: Optional[UUID] = Query(None),
        status: str = Query("open"),
        type_slug: Optional[str] = Query(None, max_length=60),
        kind: Optional[str] = Query(None),
        overdue: Optional[bool] = Query(None),
        due_from: Optional[datetime] = Query(None),
        due_to: Optional[datetime] = Query(None),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=MAX_PAGE),
        ctx: ActivitiesContext = Depends(ctx_dep),
    ) -> dict:
        me = UUID(str(ctx.user_id)) if ctx.user_id else None
        return _list(ctx, me, entity_kind, entity_id, status, type_slug, kind, overdue, due_from, due_to, page, page_size)

    @router.get("", name="activities_list")
    def list_route(
        entity_kind: Optional[str] = Query(None, max_length=60),
        entity_id: Optional[UUID] = Query(None),
        assignee_id: Optional[UUID] = Query(None),
        status: str = Query("open"),
        type_slug: Optional[str] = Query(None, max_length=60),
        kind: Optional[str] = Query(None),
        overdue: Optional[bool] = Query(None),
        due_from: Optional[datetime] = Query(None),
        due_to: Optional[datetime] = Query(None),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=MAX_PAGE),
        ctx: ActivitiesContext = Depends(ctx_dep),
    ) -> dict:
        return _list(ctx, assignee_id, entity_kind, entity_id, status, type_slug, kind, overdue, due_from, due_to, page, page_size)

    # ── one activity ──
    @router.post("", status_code=201, name="activities_create")
    def create_route(body: ActivityBody, ctx: ActivitiesContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.create_activity(scope(ctx), body.model_dump(), user_id=uid(ctx), is_member=ctx.is_member))

    @router.get("/{activity_id}", name="activities_get")
    def get_route(activity_id: UUID, ctx: ActivitiesContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.get_activity(scope(ctx), activity_id))

    @router.get("/{activity_id}/events", name="activities_events")
    def events_route(activity_id: UUID, ctx: ActivitiesContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.list_events(scope(ctx), activity_id))

    @router.patch("/{activity_id}", name="activities_edit")
    def edit_route(activity_id: UUID, body: ActivityPatch, ctx: ActivitiesContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.edit(scope(ctx), activity_id, body.model_dump(exclude_unset=True), user_id=uid(ctx)))

    @router.post("/{activity_id}/complete", name="activities_complete")
    def complete_route(activity_id: UUID, body: Optional[CompleteBody] = None, ctx: ActivitiesContext = Depends(ctx_dep)) -> dict:
        outcome = (body or CompleteBody()).outcome
        return success_response(svc.complete(scope(ctx), activity_id, outcome, user_id=uid(ctx)))

    @router.post("/{activity_id}/reopen", name="activities_reopen")
    def reopen_route(activity_id: UUID, ctx: ActivitiesContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.reopen(scope(ctx), activity_id, user_id=uid(ctx)))

    @router.post("/{activity_id}/reassign", name="activities_reassign")
    def reassign_route(activity_id: UUID, body: ReassignBody, ctx: ActivitiesContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.reassign(scope(ctx), activity_id, body.assignee_id, user_id=uid(ctx), is_member=ctx.is_member))

    @router.post("/{activity_id}/reschedule", name="activities_reschedule")
    def reschedule_route(activity_id: UUID, body: RescheduleBody, ctx: ActivitiesContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.reschedule(scope(ctx), activity_id, body.due_at, user_id=uid(ctx)))

    @router.post("/{activity_id}/cancel", name="activities_cancel")
    def cancel_route(activity_id: UUID, ctx: ActivitiesContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.cancel(scope(ctx), activity_id, user_id=uid(ctx)))

    return router


__all__ = ["make_activities_router"]
