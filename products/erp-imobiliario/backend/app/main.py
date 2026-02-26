"""
Corretor Goal Hub — FastAPI Backend

Entry point for the API server.
Run with: uvicorn app.main:app --reload --port 8000
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
    matching, condominios, ativos, clientes, metas, profiles,
    atividades, action_log, funil,
    comissoes, portais, whatsapp,
    financeiro, propostas, documentos,
    locacoes, vistorias, relatorios, distribuicao,
    marketing, agenda, dimob, ai, gamificacao,
    chaves, portal_externo, site_imoveis, campo, analise_credito, filiais,
    bi, contratos, assinaturas, portal_cliente, manutencao,
    seguros, impostos, banco, emails,
)
from app.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    generic_exception_handler,
)
from app.middleware import CorrelationIdMiddleware, RequestLoggingMiddleware
from app.logging_config import configure_logging

# Configure structured logging
configure_logging(debug=settings.debug, json_logs=not settings.debug)

# Initialize Sentry for error tracking (optional - only if SENTRY_DSN is set)
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
            profiles_sample_rate=0.1 if settings.is_production else 1.0,
            environment="production" if settings.is_production else "development",
            send_default_pii=False,
        )
        logging.info("Sentry SDK initialized successfully")
    except ImportError:
        logging.warning("Sentry SDK not installed. Error tracking disabled.")

# Create app
app = FastAPI(
    title="Corretor Goal Hub API",
    description="Backend API for real estate CRM with matching system",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
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
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With", "X-Correlation-ID", "X-Request-ID"],
    expose_headers=["X-Correlation-ID", "X-Response-Time-Ms"],
)

# Add request tracking and logging middleware
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationIdMiddleware)

# Register exception handlers for standardized error responses
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(ValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Register routers
app.include_router(ativos.router)
app.include_router(clientes.router)
app.include_router(metas.router)
app.include_router(profiles.router)
app.include_router(atividades.router)
app.include_router(action_log.router)
app.include_router(funil.router)
app.include_router(matching.router)
app.include_router(condominios.router)
app.include_router(comissoes.router)
app.include_router(portais.router)
app.include_router(whatsapp.router)
app.include_router(financeiro.router)
app.include_router(propostas.router)
app.include_router(documentos.router)
app.include_router(locacoes.router)
app.include_router(vistorias.router)
app.include_router(relatorios.router)
app.include_router(distribuicao.router)
app.include_router(chaves.router)
app.include_router(portal_externo.router)
app.include_router(site_imoveis.router)
app.include_router(campo.router)
app.include_router(analise_credito.router)
app.include_router(filiais.router)
app.include_router(marketing.router)
app.include_router(agenda.router)
app.include_router(dimob.router)
app.include_router(ai.router)
app.include_router(gamificacao.router)
app.include_router(bi.router)
app.include_router(contratos.router)
app.include_router(assinaturas.router)
app.include_router(portal_cliente.router)
app.include_router(manutencao.router)
app.include_router(seguros.router)
app.include_router(impostos.router)
app.include_router(banco.router)
app.include_router(emails.router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.2.0"}
