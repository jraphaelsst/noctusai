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
from noctusai_seed import create_product_app
from app.config import settings
from app.rate_limit import limiter
from app.routers.admin_router import router as admin_router
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

app = create_product_app(
    name="Store",
    schema="store",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    routers=[public_router, webhooks_router, admin_router],
    max_body_path_overrides=_MAX_BODY_PATH_OVERRIDES,
)
