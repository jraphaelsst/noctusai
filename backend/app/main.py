"""
Corretor Goal Hub — FastAPI Backend

Entry point for the API server.
Run with: uvicorn app.main:app --reload --port 8000
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import matching, condominios, ativos, clientes, metas, profiles, atividades, action_log, funil

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

# Create app
app = FastAPI(
    title="Corretor Goal Hub API",
    description="Backend API for real estate CRM with matching system",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow the frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.2.0"}
