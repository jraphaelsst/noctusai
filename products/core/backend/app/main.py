"""
NoctusAI Core — Main FastAPI application.

Migrated to the seed framework 2026-04-22 as part of the `core-seed-wiring`
project (closes the one documented violation of the "Seed First" rule).

Core opts into only `"health"` from the bundled standard routers because it
owns its own platform-level `notifications`, `team`, and `admin_llm_usage`
routers at `public` schema — seed's counterparts would collide. The standard
`/api/health` is inherited from the seed for uniformity with every other
product.
"""
from noctusai_seed import create_product_app

from app.config import settings
from app.rate_limit import limiter
from app.scheduler import start_scheduler, stop_scheduler
from app.routers import auth, organizations, products, licenses, sso
from app.routers import plans, subscriptions, api_keys, test_accounts, billing
from app.routers import team, roles
from app.routers import onboarding, analytics, oauth
from app.routers import entitlements, webhooks, audit_logs, audit_digest
from app.routers import settings as settings_router
from app.routers import credentials as credentials_router
from app.routers import admin_cache as admin_cache_router
from app.routers import admin_llm_usage as admin_llm_usage_router
from app.routers import admin_llm_spend as admin_llm_spend_router
from app.routers import usage
from app.routers import users
from app.routers import templates
from app.routers import me_consents as me_consents_router
from app.routers import fleet_control as fleet_control_router

app = create_product_app(
    name="Core",
    schema="public",
    settings=settings,
    version="1.0.0",
    limiter=limiter,
    lifespan_startup=start_scheduler,
    lifespan_shutdown=stop_scheduler,
    standard_routers=["health", "notificacoes", "ai_feedback", "status_paginas"],
    consent_features="app.services.ai_consent_features",
    routers=[
        auth.router,
        organizations.router,
        products.router,
        licenses.router,
        sso.router,
        plans.router,
        subscriptions.router,
        api_keys.router,
        test_accounts.router,
        billing.router,
        team.router,
        roles.router,
        onboarding.router,
        analytics.router,
        oauth.router,
        entitlements.router,
        webhooks.router,
        audit_logs.router,
        audit_digest.router,
        settings_router.router,
        credentials_router.router,
        admin_cache_router.router,
        admin_llm_usage_router.router,
        admin_llm_spend_router.router,
        usage.router,
        users.router,
        templates.router,
        me_consents_router.router,
        fleet_control_router.router,
    ],
)


@app.get("/")
async def root():
    return {
        "platform": "NoctusAI",
        "version": "1.0.0",
        "description": "AI-first ERP Platform",
    }
