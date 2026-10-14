"""Inventory HTTP surface -- `make_inventory_router(cfg, auth_dependency, admin_dependency, ...)` at `/api/inventory`.

Org STAFF may read (`auth_dependency`); every write (warehouses, receive, issue, count, transfer,
thresholds) additionally requires `admin_dependency` (the host's org-admin dep). Reservations
(`reserve/commit/release`) are NOT an HTTP surface on purpose: they are the `StockPort` other organs call
server-side from their own order lifecycle.

Same factory/DI style as `make_finance_router`: auth, the schema-scoped DB accessor and the context resolver
arrive as FastAPI dependencies. Envelopes: `{"data": ...}` / `{"data": [...], "pagination": {...}}`; errors
through the seed's `AppException` handlers.

🔴 NEVER `get_admin_client().schema(...)` in here: `get_db` already returns the product's schema-scoped client.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from noctusai_lib.primitives.responses import paginated_response, success_response

from . import reports as reports_svc
from . import stock as stock_svc
from . import warehouses as warehouses_svc
from ._common import Scope
from .config import InventoryConfig, InventoryContext
from .schemas import AdjustBody, IssueBody, MinQtyBody, ReceiveBody, TransferBody, WarehouseBody, WarehousePatch


def _dump(model: Any, **kw: Any) -> dict:
    return model.model_dump(mode="python", **kw)


def make_inventory_router(
    cfg: InventoryConfig,
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    *,
    resolve_context: Callable[[Any, Any], InventoryContext],
    get_db: Callable[..., Any],
    prefix: str = "/api/inventory",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    """Build the inventory router.

    Args:
        auth_dependency: the product's license-gated `get_current_user_org` (401 / 403 live there).
        admin_dependency: the org-admin gate; raises 403 for staff.
        resolve_context: `(auth_value, db) -> InventoryContext(db, org_id, user_id, is_admin)`.
        get_db: FastAPI dependency returning the schema-scoped client.
    """
    router = APIRouter(prefix=prefix, tags=tags or ["inventory"])

    def ctx_dep(auth=Depends(auth_dependency), db=Depends(get_db)) -> InventoryContext:
        return resolve_context(auth, db)

    def scope(ctx: InventoryContext) -> Scope:
        return Scope(ctx.db, cfg, str(ctx.org_id))

    admin = Depends(admin_dependency)

    # ── warehouses ──
    @router.get("/warehouses", name="inventory_list_warehouses")
    async def list_warehouses_route(active: Optional[bool] = Query(None), ctx: InventoryContext = Depends(ctx_dep)) -> dict:
        return success_response(warehouses_svc.list_warehouses(scope(ctx), active=active))

    @router.post("/warehouses", status_code=201, name="inventory_create_warehouse")
    async def create_warehouse_route(body: WarehouseBody, _a=admin, ctx: InventoryContext = Depends(ctx_dep)) -> dict:
        data = _dump(body, exclude={"is_default"})
        data["address"] = data["address"] or {}
        return success_response(warehouses_svc.create_warehouse(scope(ctx), data, make_default=body.is_default))

    @router.patch("/warehouses/{warehouse_id}", name="inventory_update_warehouse")
    async def update_warehouse_route(
        warehouse_id: UUID, body: WarehousePatch, _a=admin, ctx: InventoryContext = Depends(ctx_dep)
    ) -> dict:
        patch = _dump(body, exclude_unset=True, exclude={"is_default"})
        return success_response(
            warehouses_svc.update_warehouse(scope(ctx), warehouse_id, patch, make_default=body.is_default)
        )

    # ── reads ──
    @router.get("/balances", name="inventory_list_balances")
    async def list_balances_route(
        item_id: Optional[UUID] = Query(None),
        warehouse_id: Optional[UUID] = Query(None),
        include_zero: bool = Query(False),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        ctx: InventoryContext = Depends(ctx_dep),
    ) -> dict:
        rows, total, page, size = reports_svc.list_balances(
            scope(ctx), item_id=str(item_id) if item_id else None, warehouse_id=str(warehouse_id) if warehouse_id else None,
            include_zero=include_zero, page=page, page_size=page_size,
        )
        return paginated_response(rows, total, page, size)

    @router.get("/kardex", name="inventory_kardex")
    async def kardex_route(
        item_id: UUID = Query(...),
        warehouse_id: Optional[UUID] = Query(None),
        date_from: Optional[date] = Query(None, alias="from"),
        date_to: Optional[date] = Query(None, alias="to"),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        ctx: InventoryContext = Depends(ctx_dep),
    ) -> dict:
        rows, total, page, size = reports_svc.kardex(
            scope(ctx), str(item_id), warehouse_id=str(warehouse_id) if warehouse_id else None,
            date_from=date_from, date_to=date_to, page=page, page_size=page_size,
        )
        return paginated_response(rows, total, page, size)

    @router.get("/valuation", name="inventory_valuation")
    async def valuation_route(warehouse_id: Optional[UUID] = Query(None), ctx: InventoryContext = Depends(ctx_dep)) -> dict:
        return success_response(reports_svc.valuation(scope(ctx), warehouse_id=str(warehouse_id) if warehouse_id else None))

    @router.get("/low-stock", name="inventory_low_stock")
    async def low_stock_route(ctx: InventoryContext = Depends(ctx_dep)) -> dict:
        return success_response(reports_svc.low_stock(scope(ctx)))

    # ── writes ──
    @router.put("/settings", name="inventory_set_min_qty")
    async def set_min_qty_route(body: MinQtyBody, _a=admin, ctx: InventoryContext = Depends(ctx_dep)) -> dict:
        return success_response(reports_svc.set_min_qty(scope(ctx), str(body.item_id), str(body.warehouse_id), body.min_qty))

    @router.post("/receive", status_code=201, name="inventory_receive")
    async def receive_route(body: ReceiveBody, _a=admin, ctx: InventoryContext = Depends(ctx_dep)) -> dict:
        return success_response(stock_svc.receive(scope(ctx), _dump(body), user_id=str(ctx.user_id)))

    @router.post("/issue", status_code=201, name="inventory_issue")
    async def issue_route(body: IssueBody, _a=admin, ctx: InventoryContext = Depends(ctx_dep)) -> dict:
        return success_response(stock_svc.issue(scope(ctx), _dump(body), user_id=str(ctx.user_id)))

    @router.post("/adjust", status_code=201, name="inventory_adjust")
    async def adjust_route(body: AdjustBody, _a=admin, ctx: InventoryContext = Depends(ctx_dep)) -> dict:
        return success_response(stock_svc.adjust(scope(ctx), _dump(body), user_id=str(ctx.user_id)))

    @router.post("/transfer", status_code=201, name="inventory_transfer")
    async def transfer_route(body: TransferBody, _a=admin, ctx: InventoryContext = Depends(ctx_dep)) -> dict:
        return success_response(stock_svc.transfer(scope(ctx), _dump(body), user_id=str(ctx.user_id)))

    return router


__all__ = ["make_inventory_router"]
