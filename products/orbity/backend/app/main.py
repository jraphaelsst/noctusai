"""
NoctusAI Orbity — Reference Implementation

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
from app.rate_limit import limiter
from app.routers.example_router import router as example_router
from app.routers.webhook_router import router as webhook_router
from app.routers.clients_router import router as clients_router
from app.routers.crm_router import router as crm_router, capture_router
from app.routers.financial_router import router as financial_router
from app.routers.tasks_router import router as tasks_router
from app.routers.agenda_router import router as agenda_router
from app.routers.meta_ads_router import router as meta_ads_router
from app.routers.automation_router import router as automation_router
from app.routers.social_content_router import router as social_content_router, approve_router

app = create_product_app(
    name="Orbity",
    schema="orbity",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    routers=[
        example_router,
        webhook_router,
        # CRM Wave 1
        clients_router,          # /api/clients  — clients CRUD
        crm_router,              # /api/crm/*    — leads, funil, scoring
        capture_router,          # /api/capture/{org_id} — public lead capture
        # Financial Core (Wave 2)
        financial_router,        # /api/financial/* — contracts, expenses, revenues, cash-flow
        # Tasks + Agenda (Wave 2)
        tasks_router,      # /api/tasks/* + /api/routines/* — tasks, routines
        agenda_router,     # /api/agenda/events/* — calendar events + GCal sync seam
        # Meta Ads / Tráfego (Wave 3)
        meta_ads_router,   # /api/meta-ads/* — ad accounts, campaigns, metrics, sync, aggregate
        # WhatsApp Automation Flow Engine (Wave 3)
        automation_router, # /api/automation/* — flows, steps, executions, run-due
        # Social/Content Studio (Wave 3)
        social_content_router,   # /api/content/* — campaigns, posts, approvals (authed)
        approve_router,          # /api/content/approve/{token} — public client approval
    ],
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py` (each product owns its
    # consent catalog — see KB § PATTERNS/lgpd.md § 9):
    # consent_features="app.services.ai_consent_features",
)
