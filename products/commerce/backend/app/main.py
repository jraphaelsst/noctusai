"""
NoctusAI Commerce — host product of the commerce vertical seed.

Run with: uvicorn app.main:app --reload --port 8019

Mounts the noctusai_lib.domain.commerce organ routers (staff, storefront,
payment webhook) and the managed-keys router, next to the day-one skeletons.
"""
from noctusai_seed import create_product_app
from app.config import settings
from app.rate_limit import limiter
from app.routers.webhook_router import router as webhook_router
from app.routers.api_keys_router import router as api_keys_router
from app.routers.commerce_routers import payment_webhook_router, public_router, staff_router
from noctusai_lib.domain.commerce import MEDIA_UPLOAD_MAX_BYTES, MEDIA_UPLOAD_PATH_PATTERN

app = create_product_app(
    name="Commerce",
    schema="commerce",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    # Per-product routers go here. The scaffold's `example` CRUD skeleton was
    # retired once the commerce pages replaced it (P3 slice D); the signed-
    # receiver skeleton stays in ``app/routers/webhook_router.py``.
    routers=[webhook_router, staff_router, public_router, payment_webhook_router, api_keys_router],
    # The media upload is an `UploadFile` route: the 1 MB webhook default would 413 any real photo.
    max_body_path_overrides={MEDIA_UPLOAD_PATH_PATTERN: MEDIA_UPLOAD_MAX_BYTES},
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py` (each product owns its
    # consent catalog — see KB § PATTERNS/lgpd.md § 9):
    # consent_features="app.services.ai_consent_features",
)
