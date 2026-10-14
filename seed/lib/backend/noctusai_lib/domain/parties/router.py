"""Parties HTTP surface -- `make_parties_router(cfg, auth_dependency, admin_dependency, ...)` at `/api/parties`.

Authorization (same split as finance): org STAFF may read (`auth_dependency`); every write
(create, patch, roles, archive, restore, delete, CSV import) additionally requires
`admin_dependency` -- the host's org-admin dep (`require_org_admin(...)`). Unauthenticated is a
strict 401 (it lives in the host's auth dep). RLS is the floor, never the only check: every
service call is scoped by the caller's org.

Same factory shape as `make_finance_router`: the seed cannot know the product's auth or its
schema-scoped database accessor, so they arrive as FastAPI DEPENDENCIES.

Envelopes: `success_response` -> `{"data": ...}`; paged lists `paginated_response`; errors go
through the seed's `AppException` handlers -> `{"error": {"code", "message", "details"}}`.

`POST /import` is an `UploadFile` route: list `IMPORT_UPLOAD_PATH_PATTERN` in
`max_body_path_overrides` (`{IMPORT_UPLOAD_PATH_PATTERN: IMPORT_UPLOAD_MAX_BYTES}`).

🔴 NEVER `get_admin_client().schema(...)` in here: `get_db` already returns the product's
schema-scoped client.
"""
from __future__ import annotations

from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from noctusai_lib.primitives.responses import paginated_response, success_response

from . import csv_io as csv_svc
from . import parties as svc
from ._common import Scope
from .config import PartiesConfig, PartiesContext
from .schemas import PartyBody, PartyPatch, RolesBody


def _dump(model: Any, **kw: Any) -> dict:
    return model.model_dump(mode="python", **kw)


def make_parties_router(
    cfg: PartiesConfig,
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    *,
    resolve_context: Callable[[Any, Any], PartiesContext],
    get_db: Callable[..., Any],
    prefix: str = "/api/parties",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    """Build the parties router.

    Args:
        auth_dependency: the product's license-gated `get_current_user_org` (401 / 403 live there).
        admin_dependency: the org-admin gate (`require_org_admin(...)`); raises 403 for staff.
        resolve_context: `(auth_value, db) -> PartiesContext(db, org_id, user_id, is_admin)`;
            `is_admin` is decided SERVER-SIDE and only drives LGPD masking of reads.
        get_db: FastAPI dependency returning the schema-scoped client.
    """
    router = APIRouter(prefix=prefix, tags=tags or ["parties"])

    def ctx_dep(auth=Depends(auth_dependency), db=Depends(get_db)) -> PartiesContext:
        return resolve_context(auth, db)

    def scope(ctx: PartiesContext) -> Scope:
        return Scope(ctx.db, cfg, str(ctx.org_id))

    def present(ctx: PartiesContext, row: dict) -> dict:
        return svc.present_party(row, is_admin=ctx.is_admin, roles=row.get("roles"))

    admin = Depends(admin_dependency)

    @router.get("", name="parties_list")
    async def list_route(
        q: Optional[str] = Query(None, max_length=100),
        kind: Optional[str] = Query(None),
        role: Optional[str] = Query(None),
        active: Optional[bool] = Query(None),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        ctx: PartiesContext = Depends(ctx_dep),
    ) -> dict:
        rows, total, page, size = svc.list_parties(
            scope(ctx), q=q, kind=kind, role=role, active=active, page=page, page_size=page_size, is_admin=ctx.is_admin
        )
        return paginated_response([present(ctx, r) for r in rows], total, page, size)

    @router.post("", status_code=201, name="parties_create")
    async def create_route(body: PartyBody, _a=admin, ctx: PartiesContext = Depends(ctx_dep)) -> dict:
        return success_response(present(ctx, svc.create_party(scope(ctx), _dump(body))))

    @router.get("/export.csv", name="parties_export_csv")
    async def export_route(
        q: Optional[str] = Query(None, max_length=100),
        kind: Optional[str] = Query(None),
        role: Optional[str] = Query(None),
        active: Optional[bool] = Query(None),
        ctx: PartiesContext = Depends(ctx_dep),
    ) -> Response:
        data = csv_svc.parties_csv(scope(ctx), is_admin=ctx.is_admin, q=q, kind=kind, role=role, active=active)
        return Response(
            content=data, media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="cadastros.csv"'},
        )

    @router.post("/import", name="parties_import_csv")
    async def import_route(
        file: UploadFile = File(...),
        dry_run: bool = Form(False),
        _a=admin,
        ctx: PartiesContext = Depends(ctx_dep),
    ) -> dict:
        data = await file.read(csv_svc.MAX_IMPORT_BYTES + 1)  # bounded: one byte past the cap refuses without buffering the rest
        return success_response(csv_svc.import_parties(scope(ctx), data, dry_run=dry_run))

    @router.get("/{party_id}", name="parties_get")
    async def get_route(party_id: UUID, ctx: PartiesContext = Depends(ctx_dep)) -> dict:
        return success_response(present(ctx, svc.get_party(scope(ctx), party_id)))

    @router.patch("/{party_id}", name="parties_update")
    async def update_route(
        party_id: UUID, body: PartyPatch, _a=admin, ctx: PartiesContext = Depends(ctx_dep)
    ) -> dict:
        return success_response(present(ctx, svc.update_party(scope(ctx), party_id, _dump(body, exclude_unset=True))))

    @router.put("/{party_id}/roles", name="parties_set_roles")
    async def roles_route(
        party_id: UUID, body: RolesBody, _a=admin, ctx: PartiesContext = Depends(ctx_dep)
    ) -> dict:
        s = scope(ctx)
        svc.get_party(s, party_id)  # 404 before any write
        svc.set_roles(s, party_id, body.roles)
        return success_response(present(ctx, svc.get_party(s, party_id)))

    @router.post("/{party_id}/archive", name="parties_archive")
    async def archive_route(party_id: UUID, _a=admin, ctx: PartiesContext = Depends(ctx_dep)) -> dict:
        return success_response(present(ctx, svc.set_active(scope(ctx), party_id, False)))

    @router.post("/{party_id}/restore", name="parties_restore")
    async def restore_route(party_id: UUID, _a=admin, ctx: PartiesContext = Depends(ctx_dep)) -> dict:
        return success_response(present(ctx, svc.set_active(scope(ctx), party_id, True)))

    @router.delete("/{party_id}", status_code=204, name="parties_delete")
    async def delete_route(party_id: UUID, _a=admin, ctx: PartiesContext = Depends(ctx_dep)) -> Response:
        svc.delete_party(scope(ctx), party_id)
        return Response(status_code=204)

    return router


__all__ = ["make_parties_router"]
