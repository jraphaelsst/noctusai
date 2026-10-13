"""
NoctusAI Commerce — host product of the commerce vertical seed.

Run with: uvicorn app.main:app --reload --port 8019

Part 2 mounts the noctusai_lib.domain.commerce organ routers (staff,
storefront, webhook); until then the day-one skeleton routers are mounted.
"""
from noctusai_seed import create_product_app
from app.config import settings
from app.rate_limit import limiter
from app.routers.example_router import router as example_router
from app.routers.webhook_router import router as webhook_router

app = create_product_app(
    name="Commerce",
    schema="commerce",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    # Per-product routers go here. The placeholders are the canonical
    # skeletons — rename + extend per the TODO(new-product) markers in
    # ``app/routers/example_router.py`` (CRUD shape) and
    # ``app/routers/webhook_router.py`` (signed-receiver shape).
    routers=[example_router, webhook_router],
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py` (each product owns its
    # consent catalog — see KB § PATTERNS/lgpd.md § 9):
    # consent_features="app.services.ai_consent_features",
)
