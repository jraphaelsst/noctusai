"""
NoctusAI Mailing — Email Marketing & Automation Platform

Born from the seed framework. Domain routers will be added as they're built.
Run with: uvicorn app.main:app --reload --port 8006
"""
from noctusai_seed import create_product_app
from app.config import settings
from app.rate_limit import limiter

# Domain routers — uncomment as they're implemented
# from app.routers import contacts, lists, templates, campaigns
# from app.routers import automations, analytics, webhooks
# from app.routers import unsubscribe, settings as settings_router

domain_routers = [
    # contacts.router,
    # lists.router,
    # templates.router,
    # campaigns.router,
    # automations.router,
    # analytics.router,
    # webhooks.router,
    # unsubscribe.router,
    # settings_router.router,
]

app = create_product_app(
    name="Mailing",
    schema="mailing",
    settings=settings,
    routers=[r for r in domain_routers if r],
    version="0.1.0",
    limiter=limiter,
)
