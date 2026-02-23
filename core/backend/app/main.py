"""
NoctusAI Core — Main FastAPI application.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="NoctusAI Core",
    description="AI-first ERP Platform — Core API",
    version="1.0.0",
)

# CORS — restricted methods and headers for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)

# Register routers
from app.routers import auth, organizations, products, licenses, sso

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(products.router)
app.include_router(licenses.router)
app.include_router(sso.router)


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
