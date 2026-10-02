"""
NoctusAI Store — one digital product (the "Contrato Blindado" kit) sold from a
public landing page, paid through a hosted Asaas one-off charge, delivered by
email + a thank-you page, managed by a single owner at /admin.

Contract: ``products/store/projects/store-v1-CONTRACT.md``.

  * public      ``app/routers/public_router.py``   (/api/public/*, no auth, rate-limited)
  * webhook     ``app/routers/webhooks_router.py`` (/api/webhooks/asaas, verify-before-side-effect)
  * admin       ``app/routers/admin_router.py``    (/api/admin/*, owner-only via STORE_ADMIN_EMAILS)

Run with: uvicorn app.main:app --reload --port 8018
"""
from noctusai_lib.config.credentials import register_credential_override
from noctusai_lib.security.api_keys import make_local_credential_override
from noctusai_seed import create_product_app

from app.api_keys import API_KEY_SPECS, key_provider
from app.config import settings
from app.rate_limit import limiter
from app.routers.admin_router import router as admin_router
from app.routers.api_keys_router import router as api_keys_router
from app.routers.public_router import router as public_router
from app.routers.webhooks_router import router as webhooks_router

# Every `UploadFile` route needs its own body ceiling — the platform default
# (1 MB, a webhook-DoS guard) would 413 any real upload. Sized a little above
# each route's business cap (assets.MAX_PHOTO_BYTES = 5 MB, MAX_KIT_BYTES = 50 MB)
# so an over-cap file gets the route's clear 413, not an opaque outer one.
_MAX_BODY_PATH_OVERRIDES = {
    "/api/admin/autor/foto": 6 * 1024 * 1024,
    "/api/admin/produto/arquivo": 52 * 1024 * 1024,
}

# Tier-0 of the platform credential chain: lets `resolve_credential` (and so
# every seed adapter that goes through it) see the owner's DB-stored keys too.
# Registered BEFORE `create_product_app` so no request can race it — same shape
# as social-wiring's `_local_api_key` / community's.
register_credential_override(make_local_credential_override(API_KEY_SPECS, key_provider.build_store))

app = create_product_app(
    name="Store",
    schema="store",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    routers=[public_router, webhooks_router, admin_router, api_keys_router],
    max_body_path_overrides=_MAX_BODY_PATH_OVERRIDES,
)
