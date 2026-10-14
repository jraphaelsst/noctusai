"""Inventory -- stock as an L1 seed organ (roadmap E2 `inventory`, E6, E8, E12, E14).

Warehouses, an APPEND-ONLY kardex (`inv_stock_moves`), balances (`on_hand` / `reserved` / moving-average
cost), reports (balances, kardex with running balance + cost, valuation, low stock) and the `StockPort`
other organs hold stock through. Valuation is AVERAGE COST (LIFO is not permitted). Quantities are
`numeric(18,3)` (fractional KG); money is integer cents.

Overselling is impossible by construction: every mutation is a row-locked RPC that writes the move AND the
balance atomically, and `CHECK (on_hand - reserved >= 0)` is the unconditional backstop.

Mount it from a product:

    cfg = InventoryConfig(schema="erp")                         # with_items=True needs the items organ
    sql = inventory_migration(cfg, "erp")                       # -> migrations/0NN_inventory.sql
    app.include_router(make_inventory_router(cfg, auth_dependency, admin_dependency,
                                             resolve_context=..., get_db=...))
    stock = make_stock_port("supabase", db=..., cfg=cfg)        # the seam commerce / purchasing hold stock through
        # created -> stock.reserve(org, order_ref, lines) · paid -> stock.commit(...) · expired -> stock.release(...)
"""
from . import port, reports, stock, warehouses
from .config import InventoryConfig, InventoryContext
from .errors import InventoryError
from .port import FakeStockPort, NoopStockPort, StockPort, SupabaseStockPort, make_stock_port
from .router import make_inventory_router
from .sql import APPEND_ONLY_TABLES, INVENTORY_TABLES, inventory_migration
from .types import MoveKind

__all__ = [
    "APPEND_ONLY_TABLES",
    "FakeStockPort",
    "INVENTORY_TABLES",
    "InventoryConfig",
    "InventoryContext",
    "InventoryError",
    "MoveKind",
    "NoopStockPort",
    "StockPort",
    "SupabaseStockPort",
    "inventory_migration",
    "make_inventory_router",
    "make_stock_port",
    "port",
    "reports",
    "stock",
    "warehouses",
]
