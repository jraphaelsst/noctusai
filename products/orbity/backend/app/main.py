"""
NoctusAI Orbity — Agency Management Backend

Agency-management SaaS: clients, CRM funnel, tasks, agenda, financials,
Meta Ads traffic, WhatsApp automation, content/social studio, and
reports. Built on the NoctusAI seed framework — infra (auth, SSO,
notifications, team, rate limiting) comes from `create_product_app()`;
everything under `app/routers/` + `app/services/` is Orbity domain code.

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
from app.routers.clients_router import router as clients_router
from app.routers.crm_router import router as crm_router, capture_router
from app.routers.financial_router import router as financial_router
from app.routers.billing_webhook_router import router as billing_webhook_router
from app.routers.organs import contracts_organ, finance_organ, reminders_organ
from app.routers.tasks_router import router as tasks_router
from app.routers.agenda_router import router as agenda_router
from app.routers.meta_ads_router import router as meta_ads_router
from app.routers.automation_router import router as automation_router
from app.routers.social_content_router import router as social_content_router, approve_router
from app.routers.content_plans_router import router as content_plans_router
from app.routers.reports_router import router as reports_router, public_reports_router
from app.routers.whatsapp_connections_router import router as whatsapp_connections_router
from app.routers.whatsapp_webhook_router import router as whatsapp_webhook_router
from app.scheduler import configure as _configure_scheduler, start_scheduler, stop_scheduler

# Register the jobs at import (they only FIRE when NOCTUS_SCHEDULERS_ENABLED —
# the seed guard — and the lifespan hooks below start the scheduler).
_configure_scheduler()

app = create_product_app(
    name="Orbity",
    schema="orbity",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team", "status_paginas"],
    routers=[
        # CRM Wave 1
        clients_router,    # /api/clients  — clients CRUD
        crm_router,        # /api/crm/*    — leads, funil, scoring
        capture_router,    # /api/capture/{org_id} — public lead capture
        # Financial Core (Wave 2)
        financial_router,  # /api/financial/* — cash-flow (kept-charge rule), gateway charges, extra charge
        billing_webhook_router,  # /api/billing/webhook/asaas/{org_id} — gateway "paid" -> settles the receivable (token-auth)
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
        content_plans_router,    # /api/content/plans/* — monthly plans, items, tasks, AI items
        # Reports organ (Wave 3)
        reports_router,          # /api/reports/* — authenticated CRUD + generate
        public_reports_router,   # /api/reports/public/{token} — unauthenticated token read
        # WhatsApp (WAHA) — admin-managed connections + per-connection inbound webhook
        whatsapp_connections_router,  # /api/whatsapp/connections* — Conexões WhatsApp (admin)
        whatsapp_webhook_router,      # /api/whatsapp/webhook/{token} — WAHA inbound (token-auth)
    ],
    # Money lives on the seed organs: finance (/api/finance) + contracts (/api/contracts); their upload body limits ride along.
    organs=[finance_organ, contracts_organ, reminders_organ],
    lifespan_startup=start_scheduler,
    lifespan_shutdown=stop_scheduler,
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py` (each product owns its
    # consent catalog — see KB § PATTERNS/lgpd.md § 9):
    # consent_features="app.services.ai_consent_features",
)
