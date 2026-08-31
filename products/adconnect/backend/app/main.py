"""
NoctusAI AdConnect — B2B platform with products, cart, orders, rewards,
sellout, and financial modules.

Uses the seed framework for structural bones (health, CORS, logging, Sentry)
and adds domain-specific routers on top.

Run with: uvicorn app.main:app --reload --port 8007
"""
from noctusai_seed import create_product_app

from app.config import settings
from app.rate_limit import limiter
from app.routers import (
    admin,
    auth,
    cart,
    distributors,
    financial,
    orders,
    products,
    rewards,
    sellout,
)

# Domain routers with their original prefixes and tags.
#
# Phase 2 routers (products + distributors) ship their own APIRouter prefix —
# setting `router.prefix = ...` post-construction is a no-op for already-
# registered routes (FastAPI prepends router.prefix at registration time, not
# at include_router time). The legacy mock routers (cart/orders/rewards/...
# below) still rely on this assignment loop and will be migrated in their
# respective phases.
#
# Order matters: routers WITH wildcard root routes (e.g. orders.py's
# `/{order_id}` registered at the bare `/`) must come AFTER routers with
# concrete prefixes — otherwise the wildcard swallows requests for the
# concrete-prefixed routes (caught in Phase 2: `/distributors` was 404'd
# by orders.py's `/{order_id}` wildcard until distributors moved up).
_domain_routers = [
    (auth.router, "/auth", ["auth"]),
    (products.router, "/products", ["products"]),
    (distributors.router, "/distributors", ["distributors"]),
    (cart.router, "/cart", ["cart"]),
    (orders.router, "/orders", ["orders"]),
    (rewards.router, "/rewards", ["rewards"]),
    (sellout.router, "/sellout", ["sellout"]),
    (financial.router, "/financial", ["financial"]),
    # admin.router carries its own constructor-time prefix="/admin" (Phase 6).
    (admin.router, "/admin", ["admin"]),
]

# Attach prefix/tags to each router so create_product_app can include them.
# (No-op for products + distributors since they're already prefixed in their
# APIRouter constructors — the assignment is harmless and keeps the legacy
# mock routers working until they're migrated.)
for router, prefix, tags in _domain_routers:
    if not router.prefix:
        router.prefix = prefix
    if not router.tags:
        router.tags = tags

# Per-route body-size cap. The app-wide default (`settings.max_body_bytes`,
# 1 MB — see `noctusai_seed.ProductSettings`) exists to DoS-guard inbound
# webhooks; browser uploads legitimately exceed it and need their own,
# larger, per-route ceiling instead of weakening the default everywhere.
#
# 🔴 Real mounted paths — NOT `/api/sellout/...`: `sellout.router` carries
# its own constructor-time `prefix="/sellout"` (see `_domain_routers`
# above), and unlike `auth.router` (`/api/auth`) this product does not
# apply a blanket `/api` prefix at `create_product_app`-mount time either
# — routers keep exactly the prefix they declare. Confirmed against
# `routers/sellout.py`'s `APIRouter(prefix="/sellout", ...)` rather than
# inferred from the file name (see
# `noctusai_lib.api.middleware.MaxBodySizeMiddleware`'s docstring for the
# plain-prefix / wildcard-pattern shapes this dict relies on).
_MAX_BODY_PATH_OVERRIDES = {
    # NFe XML sellout report (POST /sellout/upload-nfe —
    # `routers/sellout.py::submit_nfe`). JUDGMENT CALL, not derived:
    # neither the router nor `sellout_service` enforces any size limit on
    # this upload. A nota fiscal eletrônica XML is a structured,
    # text-only document — a single NFe is typically well under 1 MB;
    # 10 MB gives generous headroom for an unusually verbose or
    # multi-item XML without treating this route like a photo/document
    # upload it structurally isn't.
    "/sellout/upload-nfe": 10 * 1024 * 1024,  # 10 MB
    # Generic sellout attachment (POST /sellout/upload-attachment —
    # `routers/sellout.py::submit_attachment`). JUDGMENT CALL, not
    # derived: same as upload-nfe, no service-side size limit exists.
    # Unlike the NFe route this accepts an arbitrary `content_type`
    # (photo, scanned document, etc.), so it gets the platform's generic
    # photo/document ceiling rather than the tighter XML-scoped one.
    "/sellout/upload-attachment": 30 * 1024 * 1024,  # 30 MB
}

app = create_product_app(
    name="AdConnect",
    schema="adconnect",
    settings=settings,
    routers=[r for r, _, _ in _domain_routers],
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team", "status_paginas"],
    max_body_path_overrides=_MAX_BODY_PATH_OVERRIDES,
)
