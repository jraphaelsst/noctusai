"""
NoctusAI Seed Product — FastAPI Backend

Entry point for the Seed Product API server.
Run with: uvicorn app.main:app --reload --port 8004
"""
import logging

from fastapi import FastAPI

from app.config import settings
from app.routers import notificacoes, team
from app.routers.health import router as health_router
from app.rate_limit import limiter
from noctusai_shared.logging_config import configure_logging
from noctusai_shared.app_factory import configure_app

configure_logging(debug=settings.debug, json_logs=not settings.debug, app_name="seed")

logger = logging.getLogger(__name__)

app = FastAPI(
    title="NoctusAI Seed Product API",
    description="Seed product — minimal viable product that proves the entire shared stack works",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Apply shared configuration (Sentry, CORS, exception handlers, middleware, rate limiting)
configure_app(app, settings, limiter=limiter)

# Register routers
app.include_router(health_router)
app.include_router(notificacoes.router)
app.include_router(team.router)
