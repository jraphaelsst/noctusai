"""
NoctusAI Daily Life — Personal Productivity Hub

Born from the seed framework. Domain routers: tasks, goals, schedule, notes, metrics.
Run with: uvicorn app.main:app --reload --port 8005
"""
from noctusai_seed import create_product_app
from app.config import settings
from app.rate_limit import limiter
from app.routers import tasks, goals, schedule, notes, metrics, ai as ai_router

app = create_product_app(
    name="Daily Life",
    schema="daily_life",
    settings=settings,
    routers=[
        tasks.router,
        goals.router,
        schedule.router,
        notes.router,
        metrics.router,
        ai_router.router,
    ],
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team", "ai_feedback"],
    consent_features="app.services.ai_consent_features",
)
