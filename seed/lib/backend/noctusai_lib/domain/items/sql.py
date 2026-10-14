"""`items_migration(cfg)` -- the items DDL for a product's schema.

Two org-scoped tables (`item_categories`, `items`) as one re-runnable migration body composed from
`noctusai_lib.domain.sql_templates` (same conventions as `finance_migration`):

- `org_id UUID NOT NULL` on every table; RLS enabled; an `authenticated` SELECT policy on
  `org_id = (SELECT <cfg.org_id_expr>)` plus the literal-named `service_role_bypass`. The backend writes
  through the service-role client, so no authenticated write policy exists.
- Forward-only and idempotent: `IF NOT EXISTS`, `DROP POLICY IF EXISTS` before each `CREATE POLICY`
  (the chain replay applies a new file twice).
- A reference never crosses tenants BY CONSTRUCTION: `UNIQUE (org_id, id)` (items too, via a re-runnable guarded DO) + composite
  `FOREIGN KEY (org_id, category_id)` -- the database refuses an item pointing at another org's category,
  independent of the service-layer check.
- The fiscal formats are CHECKed (NCM 8 digits, CEST 7, CFOP 4 with a valid first digit, origem 0..8,
  GTIN length) -- the GTIN CHECK DIGIT is validated by the service only (see ITEMS.md).
- Money is integer cents (`BIGINT`). No stock columns: the inventory organ owns stock.

Commerce link (closed 2026-10-14): `commerce_products.item_id` (nullable composite FK `(org_id, item_id)` -> this table's
`UNIQUE (org_id, id)`) ships as the commerce organ's ERP link delta (`commerce/erp_sql.py`, organ `commerce_erp`); it needs
both organs in the same schema (roadmap E5/E8).

Prerequisites (not created here): `public.current_org_id_for(text)` (core 070; the default `org_id_expr`).
"""
from __future__ import annotations

from noctusai_lib.domain._organ_common import org_rls
from noctusai_lib.domain.sql_templates import (
    set_search_path,
)

from .config import ItemsConfig
from .types import Unit, values

#: Every organ table (unprefixed), in dependency order. The generator/isolation tests iterate this --
#: a table added here without RLS fails the build.
ITEMS_TABLES: tuple[str, ...] = ("item_categories", "items")

_NIL_UUID = "00000000-0000-0000-0000-000000000000"


def _lit(vals: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in vals)


def _tables(cfg: ItemsConfig, s: str) -> list[str]:
    o = cfg.org_id_expr
    t = {name: cfg.table(name) for name in ITEMS_TABLES}
    out: list[str] = []

    def add(title: str, name: str, body: str) -> None:
        out.append(f"-- {title}\n{body.strip()}\n{org_rls(s, t[name], o)}")

    add(
        "Item categories (tree per org). Unique (org, parent, lower(name)); a parent is always in the same org.",
        "item_categories",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['item_categories']} (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    parent_id   UUID,
    name        TEXT NOT NULL CHECK (length(btrim(name)) > 0),
    is_active   BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, id),
    FOREIGN KEY (org_id, parent_id) REFERENCES {s}.{t['item_categories']} (org_id, id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['item_categories']}_name ON {s}.{t['item_categories']}
    (org_id, COALESCE(parent_id, '{_NIL_UUID}'::uuid), lower(name));
CREATE INDEX IF NOT EXISTS idx_{t['item_categories']}_parent ON {s}.{t['item_categories']} (parent_id);
""",
    )
    add(
        "Items. `sku` unique per org (case-insensitive). Fiscal fields are stored as digits-only text. "
        "`cost_cents` is informational until the inventory organ computes average cost. No stock here.",
        "items",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['items']} (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    sku           TEXT NOT NULL CHECK (sku ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{{0,63}}$'),
    name          TEXT NOT NULL CHECK (length(btrim(name)) > 0),
    description   TEXT,
    item_type     TEXT NOT NULL DEFAULT 'goods' CHECK (item_type IN ({_lit(cfg.item_types)})),
    unit          TEXT NOT NULL DEFAULT 'UN' CHECK (unit IN ({_lit(values(Unit))})),
    category_id   UUID,
    ncm           TEXT CHECK (ncm ~ '^[0-9]{{8}}$'),
    cest          TEXT CHECK (cest ~ '^[0-9]{{7}}$'),
    cfop_default  TEXT CHECK (cfop_default ~ '^[123567][0-9]{{3}}$'),
    origem        SMALLINT CHECK (origem BETWEEN 0 AND 8),
    gtin          TEXT CHECK (gtin ~ '^([0-9]{{8}}|[0-9]{{12,14}})$'),
    cost_cents    BIGINT NOT NULL DEFAULT 0 CHECK (cost_cents >= 0),
    price_cents   BIGINT CHECK (price_cents >= 0),
    weight_g      INTEGER CHECK (weight_g >= 0),
    length_mm     INTEGER CHECK (length_mm >= 0),
    width_mm      INTEGER CHECK (width_mm >= 0),
    height_mm     INTEGER CHECK (height_mm >= 0),
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (org_id, category_id) REFERENCES {s}.{t['item_categories']} (org_id, id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['items']}_sku ON {s}.{t['items']} (org_id, lower(sku));
CREATE INDEX IF NOT EXISTS idx_{t['items']}_org_name ON {s}.{t['items']} (org_id, lower(name));
CREATE INDEX IF NOT EXISTS idx_{t['items']}_category ON {s}.{t['items']} (category_id);
CREATE INDEX IF NOT EXISTS idx_{t['items']}_gtin ON {s}.{t['items']} (org_id, gtin) WHERE gtin IS NOT NULL;
-- Other organs (contracts lines, ...) reference an item through the composite FK (org_id, item_id) -> (org_id, id), which
-- Postgres only accepts against a UNIQUE (org_id, id). Added by a guarded DO so a table created by an earlier render
-- of this generator (without it) gains it on re-apply -- `ADD CONSTRAINT IF NOT EXISTS` does not exist.
DO $items_uq$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{t['items']}_org_id_id_key' AND conrelid = '{s}.{t['items']}'::regclass) THEN
        ALTER TABLE {s}.{t['items']} ADD CONSTRAINT {t['items']}_org_id_id_key UNIQUE (org_id, id);
    END IF;
END
$items_uq$;
""",
    )
    return out


def items_migration(cfg: ItemsConfig) -> str:
    """The whole items DDL for `cfg.schema`, as one re-runnable migration body (-> `migrations/0NN_items.sql`)."""
    sections = [
        "-- Items organ -- generated by noctusai_lib.domain.items.sql (do not hand-edit)",
        f"{set_search_path(cfg.schema)};",
        *_tables(cfg, cfg.schema),
    ]
    return "\n\n".join(sections) + "\n"


__all__ = ["ITEMS_TABLES", "items_migration"]
