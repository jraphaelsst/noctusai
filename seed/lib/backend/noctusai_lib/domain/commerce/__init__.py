"""Commerce -- the generic store spine, as an L1 seed organ.

Catalog (categories / products / offers / media / coupons), per-org customers with
LGPD consents + privacy requests, a quote + checkout path (price always recomputed
server-side, Asaas hosted charge with an optional noc fee split), a pure order
state machine with an append-only event trail, an idempotent payment webhook, and
the public storefront resolved from the `Host` header.

Mount it from a product (the reference host is `products/commerce`):

    cfg = CommerceConfig(schema="commerce")
    sql = commerce_migration(cfg, "commerce")                  # -> migrations/0NN_commerce.sql
    app.include_router(commerce_staff_router(cfg, auth_dependency=..., resolve_context=...,
                                             get_db=..., get_storage=..., get_cnpj_lookup=...,
                                             is_platform_admin=...))
    app.include_router(storefront_router(cfg, get_db=..., get_storage=..., get_gateway=...,
                                         get_email=..., get_license_checker=..., get_link_secret=...,
                                         rate_limit=limiter.limit))
    app.include_router(commerce_webhook_router(cfg, get_db=..., get_gateway=..., get_event_inbox=...,
                                               rate_limit=limiter.limit))

Seams (each Protocol + Fake + Real + factory): `CheckoutGateway` (per-org Asaas +
platform wallet + webhook token + gateway customer), `FulfillmentHandler` registry,
`EventInbox`, `StorageBackend`, `EmailSender`, `CnpjRegistryLookup`, `LicenseChecker`.

Contract: `projects/commerce-seed-p3/CONTRACT.md`. KB: `PATTERNS/architect/vertical-seed.md`.
"""
from . import (
    access_links,
    catalog,
    checkout,
    coupons,
    customers,
    fees,
    fiscal_retention,
    fulfillment,
    gateway,
    hosts,
    media,
    order_state,
    orders,
    profile,
    readiness,
    storefront,
    webhook,
)
from .config import CommerceConfig, CommerceContext
from .errors import (
    ACEITE_OBRIGATORIO,
    CNPJ_INVALIDO,
    VERSAO_CONFLITANTE,
    CommerceError,
    GatewayNotConfigured,
)
from .fiscal_retention import purge_expired_fiscal_retention
from .fulfillment import FulfillmentHandler, FulfillmentRegistry, NoopFulfillment, make_fulfillment_registry
from .gateway import AsaasCheckoutGateway, CheckoutGateway, FakeCheckoutGateway, make_checkout_gateway
from .media import MEDIA_UPLOAD_MAX_BYTES, MEDIA_UPLOAD_PATH_PATTERN
from .order_state import InvalidTransition, OrderEvent, transition
from .readiness import order_return_url, probe_api_key_readiness
from .router import commerce_staff_router, commerce_webhook_router, storefront_router
from .sql import APPEND_ONLY_TABLES, COMMERCE_TABLES, commerce_migration
from .types import (
    ConsentKind,
    CouponKind,
    FieldSource,
    FulfillmentType,
    MediaKind,
    OrderStatus,
    PaymentMethod,
    PrivacyRequestKind,
    ProductStatus,
    ProductType,
    TaxRegime,
    TaxTreatment,
)

__all__ = [
    "ACEITE_OBRIGATORIO",
    "APPEND_ONLY_TABLES",
    "AsaasCheckoutGateway",
    "CNPJ_INVALIDO",
    "COMMERCE_TABLES",
    "CheckoutGateway",
    "CommerceConfig",
    "CommerceContext",
    "CommerceError",
    "ConsentKind",
    "CouponKind",
    "FakeCheckoutGateway",
    "FieldSource",
    "FulfillmentHandler",
    "FulfillmentRegistry",
    "FulfillmentType",
    "GatewayNotConfigured",
    "InvalidTransition",
    "MEDIA_UPLOAD_MAX_BYTES",
    "MEDIA_UPLOAD_PATH_PATTERN",
    "MediaKind",
    "NoopFulfillment",
    "OrderEvent",
    "OrderStatus",
    "PaymentMethod",
    "PrivacyRequestKind",
    "ProductStatus",
    "ProductType",
    "TaxRegime",
    "TaxTreatment",
    "VERSAO_CONFLITANTE",
    "access_links",
    "catalog",
    "checkout",
    "commerce_migration",
    "commerce_staff_router",
    "commerce_webhook_router",
    "coupons",
    "customers",
    "fees",
    "fiscal_retention",
    "fulfillment",
    "gateway",
    "hosts",
    "make_checkout_gateway",
    "make_fulfillment_registry",
    "media",
    "order_state",
    "order_return_url",
    "orders",
    "probe_api_key_readiness",
    "purge_expired_fiscal_retention",
    "profile",
    "readiness",
    "storefront",
    "storefront_router",
    "transition",
    "webhook",
]
