"""The commerce organ's three routers, bound to this product's deps.

staff (`/api/commerce/*`, license-gated via `get_current_user_org`) · storefront
(`/api/storefront/*`, public, Host-resolved org) · payment webhook
(`/api/webhooks/payments/{gateway}/{org_id}`, verify-before-side-effect).
"""
from __future__ import annotations

from app import commerce_deps as deps
from app.commerce import CFG
from app.dependencies import get_current_user_org
from app.rate_limit import limiter
from noctusai_lib.domain.commerce import commerce_staff_router, commerce_webhook_router, storefront_router

staff_router = commerce_staff_router(
    CFG,
    auth_dependency=get_current_user_org,
    resolve_context=deps.resolve_context,
    get_db=deps.get_db,
    get_storage=deps.get_storage,
    get_cnpj_lookup=deps.get_cnpj_lookup,
    is_platform_admin=deps.is_platform_admin,
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
    rate_limit=limiter.limit,
)
