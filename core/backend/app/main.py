"""
NoctusAI Core — Main FastAPI application.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="NoctusAI Core",
    description="AI-first ERP Platform — Core API",
    version="1.0.0",
)

# CORS — restricted methods and headers for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)

# Register routers
from app.routers import auth, organizations, products, licenses, sso
from app.routers import plans, subscriptions, api_keys, test_accounts, billing
from app.routers import team, roles
from app.routers import onboarding, analytics, oauth
from app.routers import entitlements, notifications, webhooks, audit_logs

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


@app.get("/")
async def root():
    return {
        "platform": "NoctusAI",
        "version": "1.0.0",
        "description": "AI-first ERP Platform",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
