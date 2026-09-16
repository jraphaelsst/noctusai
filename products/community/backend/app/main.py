"""
NoctusAI Community — online community management center

Members, tiers, payments, WhatsApp groups, feed/forum/chat, content,
events, engagement and moderation for one paid community. Built on the
seed framework; see products/community/MASTER-PROMPT.md.

Run with: uvicorn app.main:app --reload --port 8017

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
from app.routers.aplicacoes_router import router as aplicacoes_router
from app.routers.example_router import router as example_router
from app.routers.membros_router import router as membros_router
from app.routers.planos_router import router as planos_router
from app.routers.webhook_router import router as webhook_router

app = create_product_app(
    name="Community",
    schema="community",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    # `example_router` / `webhook_router` are the inherited scaffold
    # skeletons (kept mounted — their own inherited test suite still
    # exercises the canonical shapes); `planos_router` / `membros_router`
    # / `aplicacoes_router` are module 1's real domain routers
    # (community-m1-contract.md).
    routers=[example_router, webhook_router, planos_router, membros_router, aplicacoes_router],
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py` (each product owns its
    # consent catalog — see KB § PATTERNS/lgpd.md § 9):
    # consent_features="app.services.ai_consent_features",
)
