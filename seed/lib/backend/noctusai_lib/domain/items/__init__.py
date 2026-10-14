"""Items -- the generic item master (SKU catalog with fiscal data), as an L1 seed organ.

One `itm_items` row per thing a business buys, sells, consumes or owns: SKU (unique per org), name,
`item_type` (goods | service | raw_material | asset -- a VERTICAL-SEED SEAM, extend via
`ItemsConfig.extra_item_types`), unit of measure, an org-scoped category tree, the fiscal block
(NCM, CEST, default CFOP, origem, GTIN with check digit), informational cost / reference price in integer
cents, weight and dimensions. CRUD, search, archive (items are never hard-deleted: other organs will
reference them), CSV import / export.

NOT here, on purpose: stock (the inventory organ owns it); the commerce catalog (a sales-channel concept --
roadmap E5: `commerce_products.item_id` is a nullable FK that lands with the inventory wave,
NOC-REMEDIATE[items-commerce-link] -- 2026-10-14).

Mount it from a product:

    cfg = ItemsConfig(schema="erp")
    sql = items_migration(cfg)                                # -> migrations/0NN_items.sql
    app.include_router(make_items_router(cfg, auth_dependency, admin_dependency,
                                         resolve_context=..., get_db=...))
    max_body_path_overrides[ITEMS_IMPORT_PATH_PATTERN] = ITEMS_IMPORT_MAX_BYTES

Fiscal field formats and their sources: `ITEMS.md` (next to this file).
"""
from . import categories, csv_io, items, validators
from .config import ItemsConfig, ItemsContext
from .csv_io import ITEM_CSV_COLUMNS, ITEMS_IMPORT_MAX_BYTES, ITEMS_IMPORT_PATH_PATTERN
from .errors import ItemsError
from .router import make_items_router
from .sql import ITEMS_TABLES, items_migration
from .types import ItemType, Unit

__all__ = [
    "ITEMS_IMPORT_MAX_BYTES",
    "ITEMS_IMPORT_PATH_PATTERN",
    "ITEMS_TABLES",
    "ITEM_CSV_COLUMNS",
    "ItemType",
    "ItemsConfig",
    "ItemsContext",
    "ItemsError",
    "Unit",
    "categories",
    "csv_io",
    "items",
    "items_migration",
    "make_items_router",
    "validators",
]
