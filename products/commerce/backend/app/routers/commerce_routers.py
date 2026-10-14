"""The commerce organ's routers, bound to this product's deps.

staff (`/api/commerce/*`, license-gated via `get_current_user_org`) · storefront
(`/api/storefront/*`, public, Host-resolved org) · payment webhook
(`/api/webhooks/payments/{gateway}/{org_id}`, verify-before-side-effect) · fiscal
(`/api/commerce/fiscal*`, invoices) + invoice webhook (`/api/webhooks/invoices/...`) ·
finance (`/api/finance/*`) · items (`/api/items/*`).
"""
from __future__ import annotations

from app import commerce_deps as deps
from app.commerce import CFG, SCHEMA
from app.database import _db
from app.dependencies import get_admin_client, get_current_user_org
from app.rate_limit import limiter
from noctusai_lib.domain.commerce import commerce_staff_router, commerce_webhook_router, storefront_router
from noctusai_lib.domain.commerce.fiscal_router import commerce_fiscal_router, commerce_invoice_webhook_router
from noctusai_seed.organs import ORGAN_REGISTRY, MountedOrgan, mount_finance, mount_items

staff_router = commerce_staff_router(
    CFG,
    auth_dependency=get_current_user_org,
    resolve_context=deps.resolve_context,
    get_db=deps.get_db,
    get_storage=deps.get_storage,
    get_cnpj_lookup=deps.get_cnpj_lookup,
    is_platform_admin=deps.is_platform_admin,
    admin_dependency=deps.require_org_admin,
    get_gateway=deps.get_gateway,
    get_finance=deps.get_finance,
    get_fulfillment=deps.get_fulfillment,
    get_email=deps.get_email_sender,
    on_paid_hooks=deps.ON_PAID_HOOKS,
    on_revoked_hooks=deps.ON_REVOKED_HOOKS,
)

public_router = storefront_router(
    CFG,
    get_db=deps.get_db,
    get_storage=deps.get_storage,
    get_gateway=deps.get_gateway,
    get_email=deps.get_email_sender,
    get_license_checker=deps.get_license_checker,
    get_link_secret=deps.get_link_secret,
    rate_limit=limiter.limit,
)

payment_webhook_router = commerce_webhook_router(
    CFG,
    get_db=deps.get_db,
    get_gateway=deps.get_gateway,
    get_event_inbox=deps.get_event_inbox,
    get_fulfillment=deps.get_fulfillment,
    get_finance=deps.get_finance,
    get_email=deps.get_email_sender,
    on_paid_hooks=deps.ON_PAID_HOOKS,
    on_revoked_hooks=deps.ON_REVOKED_HOOKS,
    rate_limit=limiter.limit,
)

# Fiscal (invoices): settings + certificate + issue / cancel / documents, and the provider callback.
fiscal_router = commerce_fiscal_router(
    CFG,
    auth_dependency=get_current_user_org,
    admin_dependency=deps.require_org_admin,
    resolve_context=deps.resolve_context,
    get_db=deps.get_db,
    get_storage=deps.get_storage,
    get_jobs=deps.get_jobs,
    make_provider=deps.make_provider,
    platform_admin_dependency=deps.require_platform_admin,
)

invoice_webhook_router = commerce_invoice_webhook_router(
    CFG,
    get_db=deps.get_db,
    get_storage=deps.get_storage,
    get_event_inbox=deps.get_event_inbox,
    make_provider=deps.make_provider,
    get_webhook_token=deps.get_webhook_token,
    get_jobs=deps.get_jobs,
    get_mailer=deps.get_email_sender,
    rate_limit=limiter.limit,
)

fiscal_organ = MountedOrgan(
    name="commerce_fiscal",
    routers=(fiscal_router, invoice_webhook_router),
    max_body_path_overrides=dict(ORGAN_REGISTRY["commerce_fiscal"].max_body_path_overrides()),
)

# Finance (+ statement reconciliation) and items: one-call seed mounts (routers + upload body overrides).
finance_organ = mount_finance(
    schema=SCHEMA,
    auth_dependency=get_current_user_org,
    get_admin_client=get_admin_client,
    get_core_client=lambda: _db.get_core_client(),
    get_storage=deps.get_storage,
    get_charge_operations=deps.get_charge_operations,
    default_tax_regime=deps.default_tax_regime,
)

items_organ = mount_items(
    schema=SCHEMA,
    auth_dependency=get_current_user_org,
    get_admin_client=get_admin_client,
    get_core_client=lambda: _db.get_core_client(),
)
