"""Purchasing -- purchase orders and receipts as an L1 seed organ (roadmap E2 `purchasing`, W3).

`draft -> approved -> sent -> partially_received -> received` (+ `cancelled`, only before any receipt). A RECEIPT
(partial allowed) posts, idempotently, (a) a stock `receive` move per line through the inventory organ at the LANDED
unit cost (cost + prorated freight/other - discount) and (b) the AP entries in finance (payment terms: installments,
first due in N days, interval) on the category "Mercadorias / insumos para revenda".

Approval: needs org admin or the `purchasing.approve` permission; an order ABOVE the org's
`approval_threshold_cents` (`pur_settings`) needs the permission itself (see `orders.check_can_approve`).

Mount it from a product (the organs it posts through are optional -- the default ports are Noop):

    cfg = PurchasingConfig(schema="erp")                         # with_parties / with_items / with_inventory default True
    sql = purchasing_migration(cfg, "erp")                        # -> migrations/0NN_purchasing.sql (after parties/items/inventory/finance)
    app.include_router(make_purchasing_router(cfg, auth_dependency, admin_dependency,
        resolve_context=...,        # PurchasingContext(db, org_id, user_id, is_admin, can_approve=has_permission(user, cfg.approve_permission))
        get_db=...,
        stock_factory=lambda db: make_stock_port("supabase", db=db, cfg=inventory_cfg),
        booking_factory=lambda db: make_finance_booking("supabase", db=db, cfg=FinanceConfig(schema="erp", with_parties=True))))

The finance host must mount with `with_parties=True` for the AP entry to carry `party_id` (the parties-finance link); `counterparty_*` is always a snapshot.
"""
from . import orders, receipts, settings
from .config import APPROVE_PERMISSION, DEFAULT_CATEGORY_HINT, PurchasingConfig, PurchasingContext
from .errors import PurchasingError
from .router import make_purchasing_router
from .sql import PURCHASING_TABLES, purchasing_migration
from .types import SOURCE, OrderStatus

__all__ = [
    "APPROVE_PERMISSION",
    "DEFAULT_CATEGORY_HINT",
    "OrderStatus",
    "PURCHASING_TABLES",
    "PurchasingConfig",
    "PurchasingContext",
    "PurchasingError",
    "SOURCE",
    "make_purchasing_router",
    "orders",
    "purchasing_migration",
    "receipts",
    "settings",
]
