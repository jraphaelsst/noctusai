"""
NoctusAI YouTube Crawler

YouTube Data API v3 + Drive + WAHA + SMTP — quota-aware uploads with
Fernet-encrypted refresh tokens. Scaffolded against the seed framework
2026-05-05; domain routers/services land via the implementation project
(see `products/youtube-crawler/projects/`).

Run with: uvicorn app.main:app --reload --port 8008

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

app = create_product_app(
    name="YouTube Crawler",
    schema="youtube_crawler",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py` (each product owns its
    # consent catalog — see KB § PATTERNS/lgpd.md § 9):
    # consent_features="app.services.ai_consent_features",
)
