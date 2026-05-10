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

app = create_product_app(
    name="AdConnect",
    schema="adconnect",
    settings=settings,
    routers=[r for r, _, _ in _domain_routers],
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
)
