"""Items HTTP surface -- `make_items_router(cfg, auth_dependency, admin_dependency, ...)` at `/api/items`.

Authorization (same as finance): org STAFF may read (`auth_dependency`); every write (create, update,
archive, import, categories) additionally requires `admin_dependency` -- the host's org-admin dep. RLS is
the floor, never the only check: every service call is scoped by the caller's org.

Factory (finance / commerce precedent): the seed cannot know the product's auth or its schema-scoped
database accessor, so they arrive as FastAPI DEPENDENCIES and a product keeps its own DI seams.

Envelopes: `success_response` -> `{"data": ...}`; paged lists `paginated_response`; errors go through the
seed's `AppException` handlers -> `{"error": {"code", "message", "details"}}` (pt-BR codes in `errors.py`).

HOST NOTE: `POST /api/items/import` is an `UploadFile` route -- list `ITEMS_IMPORT_PATH_PATTERN` in
`max_body_path_overrides` (`{ITEMS_IMPORT_PATH_PATTERN: ITEMS_IMPORT_MAX_BYTES}`) or the 1 MB default 413s a
real catalog.

Route order matters: the static paths (`/categories`, `/export.csv`, `/import`) are declared BEFORE
`/{item_id}`.

🔴 NEVER `get_admin_client().schema(...)` in here: `get_db` already returns the schema-scoped client.
"""
from __future__ import annotations

from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from noctusai_lib.primitives.responses import paginated_response, success_response

from . import categories as categories_svc
from . import csv_io
from . import items as items_svc
from ._common import Scope
from .config import ItemsConfig, ItemsContext
from .schemas import ItemBody, ItemCategoryBody, ItemCategoryPatch, ItemPatch


def _dump(model: Any, **kw: Any) -> dict:
    return model.model_dump(mode="python", **kw)


def make_items_router(
    cfg: ItemsConfig,
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    *,
    resolve_context: Callable[[Any, Any], ItemsContext],
    get_db: Callable[..., Any],
    prefix: str = "/api/items",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    """Build the items router.

    Args:
        auth_dependency: the product's license-gated `get_current_user_org` (401 / 403 live there).
        admin_dependency: the org-admin gate (`require_org_admin(...)`); raises 403 for staff.
        resolve_context: `(auth_value, db) -> ItemsContext(db, org_id, user_id, is_admin)`.
        get_db: FastAPI dependency returning the product's schema-scoped client.
    """
    router = APIRouter(prefix=prefix, tags=tags or ["items"])

    def ctx_dep(auth=Depends(auth_dependency), db=Depends(get_db)) -> ItemsContext:
        return resolve_context(auth, db)

    def scope(ctx: ItemsContext) -> Scope:
        return Scope(ctx.db, cfg, str(ctx.org_id))

    admin = Depends(admin_dependency)

    # ── categories (static prefix: before /{item_id}) ──
    @router.get("/categories", name="items_list_categories")
    async def list_categories_route(ctx: ItemsContext = Depends(ctx_dep)) -> dict:
        return success_response(categories_svc.list_categories(scope(ctx)))

    @router.post("/categories", status_code=201, name="items_create_category")
    async def create_category_route(body: ItemCategoryBody, _a=admin, ctx: ItemsContext = Depends(ctx_dep)) -> dict:
        return success_response(categories_svc.create_category(scope(ctx), _dump(body)))

    @router.patch("/categories/{category_id}", name="items_update_category")
    async def update_category_route(
        category_id: UUID, body: ItemCategoryPatch, _a=admin, ctx: ItemsContext = Depends(ctx_dep)
    ) -> dict:
        return success_response(categories_svc.update_category(scope(ctx), category_id, _dump(body, exclude_unset=True)))

    @router.delete("/categories/{category_id}", status_code=204, name="items_delete_category")
    async def delete_category_route(category_id: UUID, _a=admin, ctx: ItemsContext = Depends(ctx_dep)) -> Response:
        categories_svc.delete_category(scope(ctx), category_id)
        return Response(status_code=204)

    # ── CSV ──
    @router.get("/export.csv", name="items_export_csv")
    async def export_csv_route(
        q: Optional[str] = Query(None, max_length=100),
        item_type: Optional[str] = Query(None),
        category_id: Optional[UUID] = Query(None),
        active: Optional[bool] = Query(None),
        ctx: ItemsContext = Depends(ctx_dep),
    ) -> Response:
        body = csv_io.items_csv(scope(ctx), q=q, item_type=item_type, category_id=category_id, active=active)
        return Response(
            content=body,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="itens.csv"', "Cache-Control": "no-store"},
        )

    @router.post("/import", name="items_import_csv")
    async def import_csv_route(
        file: UploadFile = File(...),
        update_existing: bool = Form(False),
        dry_run: bool = Form(False),
        _a=admin,
        ctx: ItemsContext = Depends(ctx_dep),
    ) -> dict:
        # bounded read: one byte past the cap is enough to refuse with 413 without buffering the rest
        data = await file.read(csv_io.MAX_IMPORT_BYTES + 1)
        return success_response(
            csv_io.import_items_csv(scope(ctx), data, update_existing=update_existing, dry_run=dry_run)
        )

    # ── items ──
    @router.get("", name="items_list")
    async def list_items_route(
        q: Optional[str] = Query(None, max_length=100),
        item_type: Optional[str] = Query(None),
        category_id: Optional[UUID] = Query(None),
        active: Optional[bool] = Query(None),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        ctx: ItemsContext = Depends(ctx_dep),
    ) -> dict:
        rows, total, page, size = items_svc.list_items(
            scope(ctx), q=q, item_type=item_type, category_id=category_id, active=active, page=page, page_size=page_size
        )
        return paginated_response(rows, total, page, size)

    @router.post("", status_code=201, name="items_create")
    async def create_item_route(body: ItemBody, _a=admin, ctx: ItemsContext = Depends(ctx_dep)) -> dict:
        return success_response(items_svc.create_item(scope(ctx), _dump(body)))

    @router.get("/{item_id}", name="items_get")
    async def get_item_route(item_id: UUID, ctx: ItemsContext = Depends(ctx_dep)) -> dict:
        return success_response(items_svc.get_item(scope(ctx), item_id))

    @router.patch("/{item_id}", name="items_update")
    async def update_item_route(item_id: UUID, body: ItemPatch, _a=admin, ctx: ItemsContext = Depends(ctx_dep)) -> dict:
        return success_response(items_svc.update_item(scope(ctx), item_id, _dump(body, exclude_unset=True)))

    @router.post("/{item_id}/archive", name="items_archive")
    async def archive_item_route(item_id: UUID, _a=admin, ctx: ItemsContext = Depends(ctx_dep)) -> dict:
        return success_response(items_svc.set_active(scope(ctx), item_id, False))

    @router.post("/{item_id}/unarchive", name="items_unarchive")
    async def unarchive_item_route(item_id: UUID, _a=admin, ctx: ItemsContext = Depends(ctx_dep)) -> dict:
        return success_response(items_svc.set_active(scope(ctx), item_id, True))

    return router


__all__ = ["make_items_router"]
