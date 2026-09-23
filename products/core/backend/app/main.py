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
from app.scheduler import configure as configure_scheduler, start_scheduler, stop_scheduler
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
from app.routers import billing_admin as billing_admin_router
from app.routers import website_public as website_public_router
from app.routers import website_admin as website_admin_router
from app.routers.website_html import website_html_middleware

configure_scheduler()

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
        billing_admin_router.router,
        website_public_router.router,
        website_admin_router.router,
    ],
)

# Website host-split serving (contract §5) — registered as `http` middleware
# AFTER `create_product_app` returns, so it becomes the OUTERMOST layer of
# the ASGI middleware stack (Starlette's `add_middleware` prepends; the
# LAST one added runs FIRST on the way in). This intercepts a website-host
# request BEFORE it reaches any other middleware/route/the SPA mount —
# "registered before the SPA mount" in effect, since middleware wraps
# dispatch regardless of route registration order. A non-website-host
# request (e.g. `core.noctusai.com`) — or `site_enabled=false` — falls
# through to `call_next(request)` unchanged.
app.middleware("http")(website_html_middleware)


@app.get("/")
async def root():
    return {
        "platform": "NoctusAI",
        "version": "1.0.0",
        "description": "AI-first ERP Platform",
    }
