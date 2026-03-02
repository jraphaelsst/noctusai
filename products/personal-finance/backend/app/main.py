"""
NoctusAI Financas Pessoais — FastAPI Backend

Entry point for the Personal Finance API server.
Run with: uvicorn app.main:app --reload --port 8002
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
from app.routers import (
    contas, transacoes, categorias, orcamentos, metas,
    carteira, ativos, operacoes, watchlist, recorrentes,
    patrimonio, relatorios, cotacoes, dashboard,
)
from app.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    postgrest_exception_handler,
    generic_exception_handler,
)
from app.middleware import CorrelationIdMiddleware, RequestLoggingMiddleware
from app.logging_config import configure_logging

configure_logging(debug=settings.debug, json_logs=not settings.debug)

if settings.sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[
                StarletteIntegration(transaction_style="endpoint"),
                FastApiIntegration(transaction_style="endpoint"),
            ],
            traces_sample_rate=0.1 if settings.is_production else 1.0,
            environment="production" if settings.is_production else "development",
            send_default_pii=False,
        )
        logging.info("Sentry SDK initialized successfully")
    except ImportError:
        logging.warning("Sentry SDK not installed. Error tracking disabled.")

app = FastAPI(
    title="NoctusAI Financas Pessoais API",
    description="Backend API for personal finance management, investments, and portfolio tracking",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": {"code": "RATE_LIMITED", "message": "Muitas requisicoes. Tente novamente em breve."}},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With", "X-Correlation-ID", "X-Request-ID"],
    expose_headers=["X-Correlation-ID", "X-Response-Time-Ms"],
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationIdMiddleware)

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(ValidationError, validation_exception_handler)

try:
    from postgrest.exceptions import APIError as PostgRESTError
    app.add_exception_handler(PostgRESTError, postgrest_exception_handler)
except ImportError:
    pass

app.add_exception_handler(Exception, generic_exception_handler)

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


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0", "product": "personal-finance"}
