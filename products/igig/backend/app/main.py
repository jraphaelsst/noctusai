"""
NoctusAI IgIg — Reference Implementation

The simplest possible product. Just the spine, no domain code.
Proves that the seed framework works end-to-end.

Run with: uvicorn app.main:app --reload --port 8013

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
from app.rate_limit import limiter
from app.routers.cliente_router import router as cliente_router
from app.routers.example_router import router as example_router
from app.routers.webhook_router import router as webhook_router

app = create_product_app(
    name="IgIg",
    schema="igig",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    # Per-product routers go here. The placeholders are the canonical
    # skeletons — rename + extend per the TODO(new-product) markers in
    # ``app/routers/example_router.py`` (CRUD shape) and
    # ``app/routers/webhook_router.py`` (signed-receiver shape).
    routers=[cliente_router, example_router, webhook_router],
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py` (each product owns its
    # consent catalog — see KB § PATTERNS/lgpd.md § 9):
    # consent_features="app.services.ai_consent_features",
)
