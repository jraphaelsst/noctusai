"""
NoctusAI YouTube Crawler — Reference Implementation

The simplest possible product. Just the spine, no domain code.
Proves that the seed framework works end-to-end.

Run with: uvicorn app.main:app --reload --port 8010

LLM access is inherited automatically — `create_product_app()` auto-wires
credential resolution + the default multi-provider LLMConfig. If this
product grew AI features, it would call:

    from noctusai_lib.integrations.llm import chat_completion
    reply = await chat_completion(messages=[...], org_id=org_id)

…and that's all. To override the default chat model (say, prefer `gpt-4o`
over `gpt-4o-mini`):

    from noctusai_seed import default_llm_config
    app = create_product_app(
        ...,
        llm_config=default_llm_config(default_chat_model="gpt-4o"),
    )
"""
from noctusai_seed import create_product_app
from app.config import settings
from app.lifespan import on_shutdown, on_startup
from app.rate_limit import limiter
from app.routers.calendar_router import router as calendar_router
from app.routers.chat_router import router as chat_router
from app.routers.dashboard_router import router as dashboard_router
from app.routers.google_router import router as google_router
from app.routers.meta_router import router as meta_router
from app.routers.settings_router import router as settings_router, oauth_router
from app.routers.upload_router import router as upload_router
from app.routers.videos_router import router as videos_router
from app.routers.whatsapp_router import router as whatsapp_router
from app.routers.intake_monitor_router import router as intake_monitor_router

app = create_product_app(
    name="YouTube Crawler",
    schema="youtube_crawler",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team", "whatsapp_admin"],
    routers=[
        settings_router,
        oauth_router,
        upload_router,
        videos_router,
        dashboard_router,
        whatsapp_router,
        intake_monitor_router,
        chat_router,
        calendar_router,
        google_router,
        meta_router,
    ],
    # Conversation buffer + worker — boots the seed-backed
    # ConversationBufferService and the polling worker that drains the
    # debounce queue. See app/lifespan.py for the contract. WhatsApp
    # inbounds get buffered by the webhook; the worker dispatches them
    # in regex-fast-path or LLM-fallback paths after debounce expires.
    lifespan_startup=on_startup,
    lifespan_shutdown=on_shutdown,
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py` (each product owns its
    # consent catalog — see KB § PATTERNS/lgpd.md § 9):
    # consent_features="app.services.ai_consent_features",
)
