"""
NoctusAI Assistant -- a read-only shadow of one personal WhatsApp line.

* WhatsApp connection (QR, admin) + the signed inbound webhook -- `app/routers/whatsapp_router.py` (nothing else is
  mounted: no send, no mark-read, no backfill, no chat reads);
* the intake queue + its append-only events -- `app/services/intake.py`, migration 015;
* the scheduling classifier (S3, classification ONLY: no reply, no send) -- `app/shadow/`, migration 017: a seed
  `Worker` started in the lifespan + the admin replay / blind-sample routes (`app/routers/classificacao_router.py`).

Run with: uvicorn app.main:app --reload --port 8021
"""
from noctusai_lib.integrations.whatsapp import parse_line_policy, register_line_policy
from noctusai_seed import create_product_app
from app.config import settings
from app.rate_limit import limiter
from app.routers.classificacao_router import router as classificacao_router
from app.routers.google_router import callback_router as google_callback_router, router as google_router
from app.routers.whatsapp_router import router as whatsapp_router
from app.shadow.worker import start_worker, stop_worker

# Line policy v1: declare the Assistant's own line (`ASSISTANT_WAHA_LINE_POLICY`, from waha-instances.yml). A malformed
# value fails the boot; an absent one leaves the line undeclared => the seed refuses its writes (fail-closed).
if settings.assistant_waha_base_url and settings.assistant_waha_line_policy:
    register_line_policy(
        settings.assistant_waha_base_url,
        parse_line_policy(settings.assistant_waha_line_policy),
        session=settings.assistant_waha_session,
    )

app = create_product_app(
    name="Assistant",
    schema="assistant",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    # A deploy without these refuses to boot: the Fernet key (WAHA api key at rest), the webhook HMAC secret (plan
    # item 10) and the identity key (no raw third-party phone is stored).
    required_prod_config=["ENCRYPTION_KEY", "ASSISTANT_WAHA_WEBHOOK_HMAC_SECRET", "ASSISTANT_IDENTITY_HMAC_KEY"],
    routers=[whatsapp_router, classificacao_router, google_router, google_callback_router],
    lifespan_startup=start_worker,
    lifespan_shutdown=stop_worker,
)
