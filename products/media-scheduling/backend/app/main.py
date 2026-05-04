"""
NoctusAI Media Scheduling — backend app.

Phase 3 wiring:
  - Standard routers: health, notificacoes, team (seed-managed).
  - Product routers: webhooks (WAHA), oauth (Google Calendar admin +
    public init/callback), authorized_users CRUD, appointments list/detail,
    condominiums read-only.
  - Lifespan startup: `worker_lifecycle()` kicks off the conversation
    worker on a daemon thread (seed `ConversationWorker` shell + seed
    `LLMDispatcher`).

Run with: uvicorn app.main:app --reload --port 8096

LLM access is inherited automatically — `create_product_app()` auto-wires
credential resolution + the default multi-provider LLMConfig. To override
the default chat model:

    from noctusai_seed import default_llm_config
    app = create_product_app(
        ...,
        llm_config=default_llm_config(default_chat_model="gpt-4o"),
    )
"""
from noctusai_seed import create_product_app
from app.config import settings
from app.rate_limit import limiter
from app.routers import (
    appointments as appointments_router,
    authorized_users as authorized_users_router,
    condominiums as condominiums_router,
    oauth as oauth_router,
    webhooks as webhooks_router,
)
from app.workers.conversation_worker import worker_lifecycle

app = create_product_app(
    name="Media Scheduling",
    schema="media_scheduling",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    routers=[
        webhooks_router.router,
        oauth_router.public_router,
        oauth_router.admin_router,
        authorized_users_router.router,
        appointments_router.router,
        condominiums_router.router,
    ],
    lifespan_startup=worker_lifecycle,
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py` (each product owns its
    # consent catalog — see KB § PATTERNS/lgpd.md § 9):
    # consent_features="app.services.ai_consent_features",
)
