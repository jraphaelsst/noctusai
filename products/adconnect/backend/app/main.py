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

# Domain routers — each gets its own /api/<domain> prefix at construction
# time. Phase 1 of adconnect-mvp-implementation discovered that setting
# `router.prefix = "/api/<domain>"` AFTER routes are registered is NOT
# honored by FastAPI 0.115's include_router; the routes ended up at the
# bare path the route declared (e.g. `/me`, `/dist-001`) and collided.
# Wrapping each router with its prefix-set explicit FastAPI APIRouter at
# include time fixes this.
from fastapi import APIRouter as _APIRouter

_domain_routers: list[tuple[object, str, list[str]]] = [
    (auth.router, "/api/auth", ["auth"]),
    (products.router, "/api/products", ["products"]),
    (cart.router, "/api/cart", ["cart"]),
    (orders.router, "/api/orders", ["orders"]),
    (rewards.router, "/api/rewards", ["rewards"]),
    (sellout.router, "/api/sellout", ["sellout"]),
    (financial.router, "/api/financial", ["financial"]),
    (distributors.router, "/api/distributors", ["distributors"]),
    (admin.router, "/api/admin", ["admin"]),
]


def _wrap(child, prefix: str, tags: list[str]) -> _APIRouter:
    """Wrap a router with an explicit prefix + tags at include time.

    Mutating ``child.prefix`` after route registration is silently
    ignored by FastAPI's ``include_router``; nesting under a fresh
    parent applies the prefix correctly.
    """
    parent = _APIRouter(prefix=prefix, tags=tags)
    parent.include_router(child)
    return parent


_wrapped_routers = [_wrap(r, p, t) for r, p, t in _domain_routers]

app = create_product_app(
    name="AdConnect",
    schema="adconnect",
    settings=settings,
    routers=_wrapped_routers,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
)
