"""`commerce_migration(cfg, schema)` — the commerce DDL for a product's schema.

Emits EVERY CONTRACT §2 table (+ the credentials table, the payment-event inbox
and the private media bucket) as one re-runnable migration body, composed from
`noctusai_lib.domain.sql_templates` so the RLS + search_path conventions cannot
drift. Pure string emission — no IO. A product renders this verbatim into its own
`migrations/0NN_commerce.sql`; a parity test pins file == generator output.

Conventions every `commerce_*` table follows (card_hub precedent):

- `org_id UUID NOT NULL`; RLS enabled; an `authenticated` SELECT policy on
  `org_id = (SELECT public.current_org_id())` (planner-once subquery) plus the
  literal-named `service_role_bypass`. The backend writes through the
  service-role client, so no authenticated write policy exists.
- Forward-only and idempotent: `IF NOT EXISTS`, `DROP POLICY IF EXISTS` before
  each `CREATE POLICY`. (The migration-chain replay applies a new file twice.)
- Money is integer cents; timestamps are `timestamptz`.

Two deliberate exceptions to "has `org_id`": `payment_gateway_events` (the event
inbox keyed `(gateway, event_id)`, deny-all to `authenticated`) — everything else
is org-scoped.

Prerequisite (not created here): `public.current_org_id()`.
"""
from __future__ import annotations

from noctusai_lib.domain.payments.event_inbox_sql import event_inbox_table_sql
from noctusai_lib.domain.sql_templates import (
    private_org_bucket_sql,
    rls_subquery_policy,
    service_role_bypass,
    set_search_path,
)
from noctusai_lib.security.api_keys import credentials_table_ddl

from .config import CommerceConfig
from .types import (
    ConsentKind,
    CouponKind,
    FulfillmentType,
    MediaKind,
    OrderEventSource,
    OrderStatus,
    PaymentMethod,
    PrivacyRequestKind,
    PrivacyRequestStatus,
    ProductStatus,
    ProductType,
    TaxRegime,
    TaxTreatment,
    values,
)

#: Every `commerce_*` table the organ owns, in dependency order. The generator
#: test and the org-isolation test both iterate this — adding a table here
#: without RLS fails the build.
COMMERCE_TABLES: tuple[str, ...] = (
    "commerce_store_profiles",
    "commerce_store_profile_versions",
    "commerce_storefront_hosts",
    "commerce_categories",
    "commerce_products",
    "commerce_offers",
    "commerce_media",
    "commerce_coupons",
    "commerce_customers",
    "commerce_consents",
    "commerce_privacy_requests",
    "commerce_orders",
    "commerce_order_items",
    "commerce_order_events",
)

#: Tables whose rows are only ever appended (history). No authenticated write
#: policy exists on ANY table; this set documents which ones the service layer
#: also never updates/deletes (the consents' ip/user_agent scrub on anonymize is
#: the one sanctioned UPDATE — LGPD erasure beats append-only).
APPEND_ONLY_TABLES: tuple[str, ...] = (
    "commerce_store_profile_versions",
    "commerce_consents",
    "commerce_order_events",
)


def _in(enum_cls) -> str:
    return ", ".join(f"'{v}'" for v in values(enum_cls))


def _org_rls(schema: str, table: str, org_id_expr: str) -> str:
    """RLS on + own-org SELECT for `authenticated` + `service_role_bypass`."""
    select_name = f"{table}_select_own_org"
    return "\n".join(
        [
            f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;",
            f'DROP POLICY IF EXISTS "{select_name}" ON {schema}.{table};',
            rls_subquery_policy(
                schema, table, select_name, "SELECT", using=f"org_id = (SELECT {org_id_expr})"
            ),
            f'DROP POLICY IF EXISTS "service_role_bypass" ON {schema}.{table};',
            service_role_bypass(table, schema=schema),
        ]
    )


def _section(title: str, schema: str, table: str, body: str, org: str, *, extra: str = "") -> str:
    return f"-- {title}\n{body.strip()}\n{extra}{_org_rls(schema, table, org)}"


def _tables(cfg: CommerceConfig, s: str) -> list[str]:
    o = cfg.org_id_expr
    out: list[str] = []

    out.append(
        _section(
            "Store profile (one row per org; versioned ledger below). CNPJ is required.",
            s,
            "commerce_store_profiles",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_store_profiles (
    org_id           UUID PRIMARY KEY,
    version          INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    legal_name       TEXT NOT NULL,
    trade_name       TEXT NOT NULL,
    cnpj             TEXT NOT NULL,
    tax_regime       TEXT NOT NULL CHECK (tax_regime IN ({_in(TaxRegime)})),
    tax_treatment    JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    locale           TEXT NOT NULL DEFAULT 'pt-BR',
    currency         TEXT NOT NULL DEFAULT 'BRL',
    brand_tokens     JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    address          JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    contact_email    TEXT,
    contact_phone    TEXT,
    platform_fee_bps INTEGER NOT NULL DEFAULT 0 CHECK (platform_fee_bps BETWEEN 0 AND 10000),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by       UUID
);
""",
            o,
        )
    )
    out.append(
        _section(
            "Profile versions: INSERT v+1 inside the write; a PK conflict means a concurrent save (409).",
            s,
            "commerce_store_profile_versions",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_store_profile_versions (
    org_id      UUID NOT NULL,
    version     INTEGER NOT NULL,
    snapshot    JSONB NOT NULL,
    changed_by  UUID,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, version)
);
""",
            o,
        )
    )
    out.append(
        _section(
            "Storefront hosts: hostname -> org (the public storefront resolves the org from the Host header).",
            s,
            "commerce_storefront_hosts",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_storefront_hosts (
    hostname    TEXT PRIMARY KEY CHECK (hostname = lower(hostname)),
    org_id      UUID NOT NULL,
    is_primary  BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_commerce_storefront_hosts_org ON {s}.commerce_storefront_hosts (org_id);
""",
            o,
        )
    )
    out.append(
        _section(
            "Categories (tree; slug unique per org).",
            s,
            "commerce_categories",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_categories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    slug        TEXT NOT NULL,
    name        TEXT NOT NULL,
    parent_id   UUID REFERENCES {s}.commerce_categories(id) ON DELETE SET NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, slug)
);
""",
            o,
        )
    )
    out.append(
        _section(
            "Products (product_type / fulfillment_type are the seams P5 + P9 fill).",
            s,
            "commerce_products",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_products (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                 UUID NOT NULL,
    slug                   TEXT NOT NULL,
    title                  TEXT NOT NULL,
    description            TEXT NOT NULL DEFAULT '',
    product_type           TEXT NOT NULL CHECK (product_type IN ({_in(ProductType)})),
    fulfillment_type       TEXT NOT NULL CHECK (fulfillment_type IN ({_in(FulfillmentType)})),
    status                 TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ({_in(ProductStatus)})),
    category_id            UUID REFERENCES {s}.commerce_categories(id) ON DELETE SET NULL,
    attributes             JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    tax_treatment_override TEXT CHECK (tax_treatment_override IS NULL OR tax_treatment_override IN ({_in(TaxTreatment)})),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_commerce_products_org_status ON {s}.commerce_products (org_id, status);
CREATE INDEX IF NOT EXISTS idx_commerce_products_category ON {s}.commerce_products (category_id);
""",
            o,
        )
    )
    out.append(
        _section(
            "Offers (what is actually sold: price in integer cents, > 0).",
            s,
            "commerce_offers",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_offers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    product_id  UUID NOT NULL REFERENCES {s}.commerce_products(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents > 0),
    currency    TEXT NOT NULL DEFAULT 'BRL',
    active      BOOLEAN NOT NULL DEFAULT true,
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_commerce_offers_product ON {s}.commerce_offers (product_id, position);
CREATE INDEX IF NOT EXISTS idx_commerce_offers_org ON {s}.commerce_offers (org_id);
""",
            o,
        )
    )
    out.append(
        _section(
            "Media (private bucket; storage_path is org-prefixed, served only as signed URLs).",
            s,
            "commerce_media",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_media (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    product_id   UUID NOT NULL REFERENCES {s}.commerce_products(id) ON DELETE CASCADE,
    storage_path TEXT NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ({_in(MediaKind)})),
    alt          TEXT NOT NULL DEFAULT '',
    position     INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_commerce_media_product ON {s}.commerce_media (product_id, position);
CREATE INDEX IF NOT EXISTS idx_commerce_media_org ON {s}.commerce_media (org_id);
""",
            o,
        )
    )
    out.append(
        _section(
            "Coupons (percent 1-100 or fixed cents; optional window + usage cap; code unique per org, case-insensitive).",
            s,
            "commerce_coupons",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_coupons (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    code        TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ({_in(CouponKind)})),
    value       INTEGER NOT NULL CHECK (value > 0),
    starts_at   TIMESTAMPTZ,
    ends_at     TIMESTAMPTZ,
    max_uses    INTEGER CHECK (max_uses IS NULL OR max_uses > 0),
    uses_count  INTEGER NOT NULL DEFAULT 0 CHECK (uses_count >= 0),
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT commerce_coupons_percent_range CHECK (kind <> 'percent' OR value <= 100)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_commerce_coupons_org_code ON {s}.commerce_coupons (org_id, lower(code));
""",
            o,
        )
    )
    out.append(
        _section(
            "Customers (per-org buyers -- NOT noctus_users). field_sources = per-field provenance (D26).",
            s,
            "commerce_customers",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_customers (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    email          TEXT NOT NULL CHECK (email = lower(email)),
    name           TEXT NOT NULL DEFAULT '',
    doc            TEXT,
    phone          TEXT,
    address        JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    field_sources  JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    anonymized_at  TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, email)
);
""",
            o,
        )
    )
    out.append(
        _section(
            "Consents (append-only evidence: kind + legal-text version + when/where).",
            s,
            "commerce_consents",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_consents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    customer_id  UUID NOT NULL REFERENCES {s}.commerce_customers(id) ON DELETE CASCADE,
    order_id     UUID,
    kind         TEXT NOT NULL CHECK (kind IN ({_in(ConsentKind)})),
    version      TEXT NOT NULL,
    granted      BOOLEAN NOT NULL,
    ip           TEXT,
    user_agent   TEXT,
    at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_commerce_consents_customer ON {s}.commerce_consents (customer_id, at DESC);
CREATE INDEX IF NOT EXISTS idx_commerce_consents_org ON {s}.commerce_consents (org_id);
""",
            o,
        )
    )
    out.append(
        _section(
            "Privacy requests (LGPD art. 18) -- verified by an e-mailed link before anyone acts on them.",
            s,
            "commerce_privacy_requests",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_privacy_requests (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    customer_id  UUID NOT NULL REFERENCES {s}.commerce_customers(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL CHECK (kind IN ({_in(PrivacyRequestKind)})),
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ({_in(PrivacyRequestStatus)})),
    details      TEXT,
    verified_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_commerce_privacy_requests_customer ON {s}.commerce_privacy_requests (customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_commerce_privacy_requests_org ON {s}.commerce_privacy_requests (org_id, status);
""",
            o,
        )
    )
    out.append(
        _section(
            "Orders. token = the opaque public handle; platform_fee_cents is the EXPECTED noc fee (D27). buyer_doc/buyer_name/fiscal_retain_until = the D30 tax-record snapshot taken at `paid` (LGPD art. 16 II + CTN art. 173).",
            s,
            "commerce_orders",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_orders (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             UUID NOT NULL,
    token              TEXT NOT NULL UNIQUE,
    customer_id        UUID NOT NULL REFERENCES {s}.commerce_customers(id),
    status             TEXT NOT NULL DEFAULT 'created' CHECK (status IN ({_in(OrderStatus)})),
    subtotal_cents     INTEGER NOT NULL CHECK (subtotal_cents >= 0),
    discount_cents     INTEGER NOT NULL DEFAULT 0 CHECK (discount_cents >= 0),
    total_cents        INTEGER NOT NULL CHECK (total_cents >= 0),
    currency           TEXT NOT NULL DEFAULT 'BRL',
    coupon_id          UUID REFERENCES {s}.commerce_coupons(id) ON DELETE SET NULL,
    payment_method     TEXT NOT NULL CHECK (payment_method IN ({_in(PaymentMethod)})),
    gateway            TEXT NOT NULL,
    gateway_charge_id  TEXT,
    checkout_url       TEXT,
    pix_qr             JSONB,
    expires_at         TIMESTAMPTZ,
    paid_at            TIMESTAMPTZ,
    platform_fee_cents INTEGER NOT NULL DEFAULT 0 CHECK (platform_fee_cents >= 0),
    buyer_doc          TEXT,
    buyer_name         TEXT,
    fiscal_retain_until DATE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_commerce_orders_fiscal_retain ON {s}.commerce_orders (fiscal_retain_until)
    WHERE fiscal_retain_until IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_commerce_orders_org_created ON {s}.commerce_orders (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_commerce_orders_org_status ON {s}.commerce_orders (org_id, status);
CREATE INDEX IF NOT EXISTS idx_commerce_orders_customer ON {s}.commerce_orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_commerce_orders_charge ON {s}.commerce_orders (gateway_charge_id)
    WHERE gateway_charge_id IS NOT NULL;
""",
            o,
        )
    )
    out.append(
        _section(
            "Order items: a SNAPSHOT of what was sold (history survives a product/offer deletion).",
            s,
            "commerce_order_items",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_order_items (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    order_id         UUID NOT NULL REFERENCES {s}.commerce_orders(id) ON DELETE CASCADE,
    product_id       UUID REFERENCES {s}.commerce_products(id) ON DELETE SET NULL,
    offer_id         UUID REFERENCES {s}.commerce_offers(id) ON DELETE SET NULL,
    title_snapshot   TEXT NOT NULL,
    product_type     TEXT NOT NULL CHECK (product_type IN ({_in(ProductType)})),
    fulfillment_type TEXT NOT NULL CHECK (fulfillment_type IN ({_in(FulfillmentType)})),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents > 0),
    qty              INTEGER NOT NULL CHECK (qty > 0),
    total_cents      INTEGER NOT NULL CHECK (total_cents > 0)
);
CREATE INDEX IF NOT EXISTS idx_commerce_order_items_order ON {s}.commerce_order_items (order_id);
CREATE INDEX IF NOT EXISTS idx_commerce_order_items_org ON {s}.commerce_order_items (org_id);
""",
            o,
        )
    )
    out.append(
        _section(
            "Order events (append-only): every applied transition leaves a row.",
            s,
            "commerce_order_events",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_order_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    order_id     UUID NOT NULL REFERENCES {s}.commerce_orders(id) ON DELETE CASCADE,
    from_status  TEXT CHECK (from_status IS NULL OR from_status IN ({_in(OrderStatus)})),
    to_status    TEXT NOT NULL CHECK (to_status IN ({_in(OrderStatus)})),
    reason       TEXT,
    source       TEXT NOT NULL CHECK (source IN ({_in(OrderEventSource)})),
    at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_commerce_order_events_order ON {s}.commerce_order_events (order_id, at);
CREATE INDEX IF NOT EXISTS idx_commerce_order_events_org ON {s}.commerce_order_events (org_id);
""",
            o,
        )
    )
    return out


def commerce_migration(cfg: CommerceConfig, schema: str) -> str:
    """The whole commerce DDL for `schema`, as one re-runnable migration body.

    Includes: the 14 `COMMERCE_TABLES`, the per-org Fernet `credentials` table
    (Asaas keys), the `payment_gateway_events` inbox, and the private media
    bucket with per-org object RLS. Prerequisite: `public.current_org_id()`.
    """
    if not schema or not schema.strip():
        raise ValueError("commerce_migration requires a non-empty schema")
    sections = [
        "-- Commerce organ -- generated by noctusai_lib.domain.commerce.sql (do not hand-edit)",
        f"{set_search_path(schema)};",
        *_tables(cfg, schema),
        "-- Per-org payment-gateway credentials (Fernet-encrypted; Asaas key + webhook token).\n"
        + credentials_table_ddl(schema, idempotent=True),
        "-- Webhook idempotency inbox (RealSupabaseEventInbox).\n" + event_inbox_table_sql(schema),
        private_org_bucket_sql(
            cfg.bucket,
            comment="Private media bucket; object RLS keys on the org_id first path segment.",
        ),
    ]
    return "\n\n".join(sections) + "\n"


__all__ = ["APPEND_ONLY_TABLES", "COMMERCE_TABLES", "commerce_migration"]
