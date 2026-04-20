"""
NoctusAI Core — Main FastAPI application.
"""
from fastapi import FastAPI
from app.config import settings
from app.rate_limit import limiter
from app.logging_config import configure_logging
from noctusai_lib.app_factory import configure_app

configure_logging(debug=settings.debug, json_logs=not settings.debug)

app = FastAPI(
    title="NoctusAI Core",
    description="AI-first ERP Platform — Core API",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Apply shared configuration (Sentry, CORS, exception handlers, middleware, rate limiting)
configure_app(app, settings, limiter=limiter)

# Register routers
from app.routers import auth, organizations, products, licenses, sso
from app.routers import plans, subscriptions, api_keys, test_accounts, billing
from app.routers import team, roles
from app.routers import onboarding, analytics, oauth
from app.routers import entitlements, notifications, webhooks, audit_logs
from app.routers import settings as settings_router
from app.routers import credentials as credentials_router
from app.routers import admin_cache as admin_cache_router
from app.routers import usage
from app.routers import users
from app.routers import templates

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(products.router)
app.include_router(licenses.router)
app.include_router(sso.router)
app.include_router(plans.router)
app.include_router(subscriptions.router)
app.include_router(api_keys.router)
app.include_router(test_accounts.router)
app.include_router(billing.router)
app.include_router(team.router)
app.include_router(roles.router)
app.include_router(onboarding.router)
app.include_router(analytics.router)
app.include_router(oauth.router)
app.include_router(entitlements.router)
app.include_router(notifications.router)
app.include_router(webhooks.router)
app.include_router(audit_logs.router)
app.include_router(settings_router.router)
app.include_router(credentials_router.router)
app.include_router(admin_cache_router.router)
app.include_router(usage.router)
app.include_router(users.router)
app.include_router(templates.router)


@app.get("/")
async def root():
    return {
        "platform": "NoctusAI",
        "version": "1.0.0",
        "description": "AI-first ERP Platform",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "product": "core", "version": "1.0.0"}
