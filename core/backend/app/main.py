"""
NoctusAI Core — Main FastAPI application.
"""
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.config import settings
from app.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    postgrest_exception_handler,
    generic_exception_handler,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

app = FastAPI(
    title="NoctusAI Core",
    description="AI-first ERP Platform — Core API",
    version="1.0.0",
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": {"code": "RATE_LIMITED", "message": "Muitas requisições. Tente novamente em breve."}},
    )

# CORS — restricted methods and headers for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)

# Register exception handlers for standardized error responses
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(ValidationError, validation_exception_handler)

# Handle PostgREST errors (e.g. .single() with 0 rows → 404 instead of 500)
try:
    from postgrest.exceptions import APIError as PostgRESTError
    app.add_exception_handler(PostgRESTError, postgrest_exception_handler)
except ImportError:
    pass

app.add_exception_handler(Exception, generic_exception_handler)

# Register routers
from app.routers import auth, organizations, products, licenses, sso
from app.routers import plans, subscriptions, api_keys, test_accounts, billing
from app.routers import team, roles
from app.routers import onboarding, analytics, oauth
from app.routers import entitlements, notifications, webhooks, audit_logs
from app.routers import settings

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
app.include_router(settings.router)


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
