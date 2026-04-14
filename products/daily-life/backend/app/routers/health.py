"""
Health check endpoint for the Daily Life Product API.
"""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check():
    """Return service health status."""
    return {"status": "ok", "product": "Daily Life", "version": "0.1.0"}
