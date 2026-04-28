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

# Domain routers with their original prefixes and tags
_domain_routers = [
    (auth.router, "/auth", ["auth"]),
    (products.router, "/products", ["products"]),
    (cart.router, "/cart", ["cart"]),
    (orders.router, "/orders", ["orders"]),
    (rewards.router, "/rewards", ["rewards"]),
    (sellout.router, "/sellout", ["sellout"]),
    (financial.router, "/financial", ["financial"]),
    (distributors.router, "/distributors", ["distributors"]),
    (admin.router, "/admin", ["admin"]),
]

# Attach prefix/tags to each router so create_product_app can include them
for router, prefix, tags in _domain_routers:
    router.prefix = prefix
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
