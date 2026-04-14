"""
NoctusAI Financas Pessoais — FastAPI Backend

Entry point for the Personal Finance API server.
Run with: uvicorn app.main:app --reload --port 8002
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.scheduler import start_scheduler, stop_scheduler
from app.routers import (
    contas, transacoes, categorias, orcamentos, metas,
    carteira, ativos, operacoes, watchlist, recorrentes,
    patrimonio, relatorios, cotacoes, dashboard,
    notificacoes, team,
)
from app.rate_limit import limiter
from app.logging_config import configure_logging
from noctusai_shared.app_factory import configure_app

configure_logging(debug=settings.debug, json_logs=not settings.debug)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="NoctusAI Financas Pessoais API",
    description="Backend API for personal finance management, investments, and portfolio tracking",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# Apply shared configuration (Sentry, CORS, exception handlers, middleware, rate limiting)
configure_app(app, settings, limiter=limiter)

# Register routers
app.include_router(contas.router)
app.include_router(transacoes.router)
app.include_router(categorias.router)
app.include_router(orcamentos.router)
app.include_router(metas.router)
app.include_router(carteira.router)
app.include_router(ativos.router)
app.include_router(operacoes.router)
app.include_router(watchlist.router)
app.include_router(recorrentes.router)
app.include_router(patrimonio.router)
app.include_router(relatorios.router)
app.include_router(cotacoes.router)
app.include_router(dashboard.router)
app.include_router(notificacoes.router)
app.include_router(team.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0", "product": "personal-finance"}
