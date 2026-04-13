"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "product": "{{PRODUCT_SLUG}}"}
