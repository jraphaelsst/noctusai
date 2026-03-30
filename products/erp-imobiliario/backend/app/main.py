"""
Corretor Goal Hub — FastAPI Backend

Entry point for the API server.
Run with: uvicorn app.main:app --reload --port 8001
"""
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI

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
    notificacoes, whatsapp_webhook, meta_api,
    storage, pdf, jobs, recorrencia,
    certidoes,
    matriculas,
    configuracoes,
)
from app.rate_limit import limiter
from app.logging_config import configure_logging
from app.services.certidoes_service import recover_stuck_processando, schedule_all_pending_tjsp
from app.dependencies import get_admin_client
from noctusai_shared.app_factory import configure_app

logger = logging.getLogger(__name__)

# Configure structured logging
configure_logging(debug=settings.debug, json_logs=not settings.debug)

# Production safety checks
if not settings.debug and not settings.jwt_secret:
    raise RuntimeError(
        "JWT_SECRET must be set in production. "
        "Set DEBUG=true for development or provide a secure JWT_SECRET."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Recover stuck items and schedule pending TJSP on startup."""
    admin_db = get_admin_client()
    recover_stuck_processando(admin_db)
    schedule_all_pending_tjsp(admin_db)
    yield


# Create app
app = FastAPI(
    title="Corretor Goal Hub API",
    description="Backend API for real estate CRM with matching system",
    version="0.2.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# Apply shared configuration (Sentry, CORS, exception handlers, middleware, rate limiting)
configure_app(
    app, settings, limiter=limiter,
    cors_expose_headers=[
        "X-Correlation-ID", "X-Response-Time-Ms", "Content-Disposition",
    ],
)

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
app.include_router(notificacoes.router)
app.include_router(whatsapp_webhook.router)
app.include_router(meta_api.router)
app.include_router(storage.router)
app.include_router(pdf.router)
app.include_router(jobs.router)
app.include_router(recorrencia.router)
app.include_router(certidoes.router)
app.include_router(matriculas.router)
app.include_router(configuracoes.router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.2.0"}
