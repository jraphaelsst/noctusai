"""Purchasing HTTP surface -- `make_purchasing_router(cfg, auth_dependency, admin_dependency, ...)` at `/api/purchasing`.

Org STAFF may read (`auth_dependency`); writes (save / send / cancel / receive / repost / settings) additionally require
`admin_dependency` (the host's org-admin dep -- the organ never re-implements the admin check). APPROVAL is NOT
admin-gated at the door: it needs only an authenticated caller, then `orders.check_can_approve` decides on `ctx.is_admin`
and membership in THIS org's approver list (`pur_approvers`, read here -- never host-supplied, never a global permission).
Changing the approval threshold (`PUT /settings`) needs an approver of the org; the approver list itself is managed by org
admins (`/approvers`). The limit + cooldown are enforced by the `pur_transition` RPC under the order lock.

Cross-organ legs arrive as per-request factories (`stock_factory(db) -> StockPort`, `booking_factory(db) ->
FinanceBooking`); the defaults are the Noop ports, i.e. a host that does not mount inventory / finance simply posts nothing.

🔴 NEVER `get_admin_client().schema(...)` in here: `get_db` already returns the product's schema-scoped client.
"""
from __future__ import annotations

from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from noctusai_lib.domain.finance.booking import FinanceBooking, NoopFinanceBooking
from noctusai_lib.domain.inventory.port import NoopStockPort, StockPort
from noctusai_lib.primitives.responses import paginated_response, success_response

from . import approvers as approvers_svc
from . import orders as orders_svc
from . import receipts as receipts_svc
from . import settings as settings_svc
from ._common import Scope
from .config import PurchasingConfig, PurchasingContext
from .errors import SEM_PERMISSAO_LIMITE, forbidden, invalid
from .schemas import ApproverBody, CancelBody, OrderBody, ReceiptBody, SettingsBody
from .types import OrderStatus, values


def _dump(model: Any, **kw: Any) -> dict:
    return model.model_dump(mode="python", **kw)


def make_purchasing_router(
    cfg: PurchasingConfig,
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    *,
    resolve_context: Callable[[Any, Any], PurchasingContext],
    get_db: Callable[..., Any],
    stock_factory: Callable[[Any], StockPort] = lambda db: NoopStockPort(),
    booking_factory: Callable[[Any], FinanceBooking] = lambda db: NoopFinanceBooking(),
    prefix: str = "/api/purchasing",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    """Build the purchasing router.

    Args:
        auth_dependency: the product's license-gated `get_current_user_org` (401 / 403 live there).
        admin_dependency: the org-admin gate; raises 403 for staff.
        resolve_context: `(auth_value, db) -> PurchasingContext(db, org_id, user_id, is_admin)`.
        get_db: FastAPI dependency returning the schema-scoped client.
        stock_factory / booking_factory: build the inventory / finance seam for a request's `db`.
    """
    router = APIRouter(prefix=prefix, tags=tags or ["purchasing"])

    def ctx_dep(auth=Depends(auth_dependency), db=Depends(get_db)) -> PurchasingContext:
        return resolve_context(auth, db)

    def scope(ctx: PurchasingContext) -> Scope:
        return Scope(ctx.db, cfg, str(ctx.org_id))

    admin = Depends(admin_dependency)

    def approver_dep(ctx: PurchasingContext = Depends(ctx_dep)) -> bool:
        """Is the caller in THIS org's approver list (the selected org from `ctx`, nothing else)?"""
        return approvers_svc.is_approver(scope(ctx), ctx.user_id)

    # ── settings ──
    @router.get("/settings", name="purchasing_get_settings")
    async def get_settings_route(ctx: PurchasingContext = Depends(ctx_dep), is_approver: bool = Depends(approver_dep)) -> dict:
        return success_response({**settings_svc.get_settings(scope(ctx)), "is_approver": is_approver})

    @router.put("/settings", name="purchasing_set_settings")
    async def set_settings_route(
        body: SettingsBody, ctx: PurchasingContext = Depends(ctx_dep), is_approver: bool = Depends(approver_dep)
    ) -> dict:
        # Auth-only at the door; the ROUTE decides: moving the limit is an approver's act (an org admin who is not one
        # adds themselves first -- that grant is audit-logged). The change + its audit row + the cooldown are one RPC.
        if not is_approver:
            raise forbidden(SEM_PERMISSAO_LIMITE, "Alterar o limite de aprovação exige ser aprovador desta organização.")
        return success_response(settings_svc.set_threshold(scope(ctx), body.approval_threshold_cents, user_id=str(ctx.user_id)))

    # ── approvers (org admin) ──
    @router.get("/approvers", name="purchasing_list_approvers")
    async def list_approvers_route(_a=admin, ctx: PurchasingContext = Depends(ctx_dep)) -> dict:
        return success_response(approvers_svc.list_approvers(scope(ctx)))

    @router.post("/approvers", status_code=201, name="purchasing_add_approver")
    async def add_approver_route(body: ApproverBody, _a=admin, ctx: PurchasingContext = Depends(ctx_dep)) -> dict:
        return success_response(approvers_svc.set_approver(scope(ctx), body.user_id, granted=True, actor_id=ctx.user_id))

    @router.delete("/approvers/{user_id}", name="purchasing_remove_approver")
    async def remove_approver_route(user_id: UUID, _a=admin, ctx: PurchasingContext = Depends(ctx_dep)) -> dict:
        return success_response(approvers_svc.set_approver(scope(ctx), user_id, granted=False, actor_id=ctx.user_id))

    # ── orders ──
    @router.get("/orders", name="purchasing_list_orders")
    async def list_orders_route(
        status: Optional[str] = Query(None),
        party_id: Optional[UUID] = Query(None),
        q: Optional[str] = Query(None, max_length=100),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
        ctx: PurchasingContext = Depends(ctx_dep),
    ) -> dict:
        if status is not None and status not in values(OrderStatus):
            raise invalid("status", "Status inválido.")
        rows, total, page, size = orders_svc.list_orders(
            scope(ctx), status=status, party_id=str(party_id) if party_id else None, q=q, page=page, page_size=page_size
        )
        return paginated_response(rows, total, page, size)

    @router.post("/orders", status_code=201, name="purchasing_create_order")
    async def create_order_route(body: OrderBody, _a=admin, ctx: PurchasingContext = Depends(ctx_dep)) -> dict:
        return success_response(orders_svc.save_order(scope(ctx), None, _dump(body), user_id=str(ctx.user_id)))

    @router.get("/orders/{order_id}", name="purchasing_get_order")
    async def get_order_route(order_id: UUID, ctx: PurchasingContext = Depends(ctx_dep)) -> dict:
        return success_response(orders_svc.get_order(scope(ctx), order_id))

    @router.put("/orders/{order_id}", name="purchasing_replace_order")
    async def replace_order_route(order_id: UUID, body: OrderBody, _a=admin, ctx: PurchasingContext = Depends(ctx_dep)) -> dict:
        return success_response(orders_svc.save_order(scope(ctx), order_id, _dump(body), user_id=str(ctx.user_id)))

    @router.post("/orders/{order_id}/approve", name="purchasing_approve_order")
    async def approve_order_route(
        order_id: UUID, ctx: PurchasingContext = Depends(ctx_dep), is_approver: bool = Depends(approver_dep)
    ) -> dict:
        return success_response(
            orders_svc.approve_order(scope(ctx), order_id, user_id=str(ctx.user_id), is_admin=ctx.is_admin, can_approve=is_approver)
        )

    @router.post("/orders/{order_id}/send", name="purchasing_send_order")
    async def send_order_route(order_id: UUID, _a=admin, ctx: PurchasingContext = Depends(ctx_dep)) -> dict:
        return success_response(orders_svc.send_order(scope(ctx), order_id, user_id=str(ctx.user_id)))

    @router.post("/orders/{order_id}/cancel", name="purchasing_cancel_order")
    async def cancel_order_route(order_id: UUID, body: CancelBody, _a=admin, ctx: PurchasingContext = Depends(ctx_dep)) -> dict:
        return success_response(orders_svc.cancel_order(scope(ctx), order_id, user_id=str(ctx.user_id), reason=body.reason))

    # ── receipts ──
    @router.post("/orders/{order_id}/receipts", status_code=201, name="purchasing_receive_order")
    async def receive_order_route(order_id: UUID, body: ReceiptBody, _a=admin, ctx: PurchasingContext = Depends(ctx_dep)) -> dict:
        return success_response(
            receipts_svc.receive(
                scope(ctx), order_id, _dump(body), user_id=str(ctx.user_id),
                stock=stock_factory(ctx.db), booking=booking_factory(ctx.db),
            )
        )

    @router.get("/receipts", name="purchasing_list_receipts")
    async def list_receipts_route(
        order_id: Optional[UUID] = Query(None),
        pending: bool = Query(False),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
        ctx: PurchasingContext = Depends(ctx_dep),
    ) -> dict:
        rows, total, page, size = receipts_svc.list_receipts(
            scope(ctx), order_id=str(order_id) if order_id else None, pending_only=pending, page=page, page_size=page_size
        )
        return paginated_response(rows, total, page, size)

    @router.get("/receipts/{receipt_id}", name="purchasing_get_receipt")
    async def get_receipt_route(receipt_id: UUID, ctx: PurchasingContext = Depends(ctx_dep)) -> dict:
        return success_response(receipts_svc.get_receipt(scope(ctx), receipt_id))

    @router.post("/receipts/{receipt_id}/post", name="purchasing_post_receipt")
    async def post_receipt_route(receipt_id: UUID, _a=admin, ctx: PurchasingContext = Depends(ctx_dep)) -> dict:
        return success_response(
            receipts_svc.post_receipt(
                scope(ctx), receipt_id, user_id=str(ctx.user_id), stock=stock_factory(ctx.db), booking=booking_factory(ctx.db)
            )
        )

    return router


__all__ = ["make_purchasing_router"]
