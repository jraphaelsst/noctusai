"""
NoctusAI Mailing — Email Marketing & Automation Platform

Born from the seed framework. Full domain: contacts, lists, templates,
campaigns, automations, analytics, webhooks, unsubscribe, settings.
Run with: uvicorn app.main:app --reload --port 8006
"""
from noctusai_seed import create_product_app
from app.config import settings
from app.rate_limit import limiter
from app.scheduler import start_scheduler, stop_scheduler
from app.routers import (
    contacts, lists, templates, campaigns,
    automations, analytics, webhooks, unsubscribe,
)
from app.routers import settings as settings_router

app = create_product_app(
    name="Mailing",
    schema="mailing",
    settings=settings,
    routers=[
        contacts.router,
        lists.router,
        templates.router,
        campaigns.router,
        automations.router,
        analytics.router,
        webhooks.router,
        unsubscribe.router,
        settings_router.router,
    ],
    version="0.1.0",
    limiter=limiter,
    lifespan_startup=start_scheduler,
    lifespan_shutdown=stop_scheduler,
)
