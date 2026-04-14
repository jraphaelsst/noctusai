"""
{{PRODUCT_NAME}} — FastAPI Backend
"""
from fastapi import FastAPI
from noctusai_shared.app_factory import configure_app
from app.config import settings
from app.rate_limit import limiter
from app.routers import health, notificacoes

app = FastAPI(
    title="NoctusAI {{PRODUCT_NAME}} API",
    description="Backend API for {{PRODUCT_NAME}}",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

configure_app(app, settings, limiter=limiter)

# Register routers
app.include_router(health.router)
app.include_router(notificacoes.router)

# Add your product routers here:
# from app.routers import your_router
# app.include_router(your_router.router)
