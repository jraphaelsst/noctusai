"""
Health check endpoint for the {{PRODUCT_NAME}} API.
"""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check():
    """Return service health status."""
    return {"status": "ok", "product": "{{PRODUCT_NAME}}", "version": "0.1.0"}
