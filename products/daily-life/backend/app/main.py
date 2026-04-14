"""
NoctusAI Daily Life — FastAPI Backend

Personal productivity hub: tasks, goals, habits, schedule, notes, automations.
Run with: uvicorn app.main:app --reload --port 8005
"""
import logging

from fastapi import FastAPI

from app.config import settings
from app.routers import notificacoes, team, tasks, goals, schedule, notes, focus, metrics
from app.routers.health import router as health_router
from app.rate_limit import limiter
from noctusai_shared.logging_config import configure_logging
from noctusai_shared.app_factory import configure_app

configure_logging(debug=settings.debug, json_logs=not settings.debug, app_name="daily-life")

logger = logging.getLogger(__name__)

app = FastAPI(
    title="NoctusAI Daily Life API",
    description="Personal productivity hub — tasks, goals, habits, schedule, notes, automations",
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
app.include_router(tasks.router)
app.include_router(goals.router)
app.include_router(schedule.router)
app.include_router(notes.router)
app.include_router(focus.router)
app.include_router(metrics.router)
