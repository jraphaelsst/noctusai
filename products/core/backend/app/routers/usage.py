"""
Usage Reporting Router — Product usage metrics for admin dashboards.

GET  /api/admin/usage              — Latest usage metrics for all products (admin)
GET  /api/admin/usage/{org_id}     — Usage metrics for a specific org (admin)
GET  /api/usage/me                 — Usage metrics for current user's org
POST /api/admin/usage/snapshot     — Trigger a manual usage snapshot (admin)
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_admin, get_org_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Usage"])


@router.get("/api/admin/usage")
async def get_all_usage(authorization: Optional[str] = Header(None)):
    """Get latest usage metrics for all orgs and products (admin only)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("product_usage").select(
        "*, products(nome, slug), organizations(nome)"
    ).order("recorded_at", desc=True).limit(100).execute()

    return {"data": result.data or []}


@router.get("/api/admin/usage/{org_id}")
async def get_org_usage(org_id: str, authorization: Optional[str] = Header(None)):
    """Get usage metrics for a specific org (admin only)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    result = db.table("product_usage").select(
        "*, products(nome, slug)"
    ).eq("org_id", org_id).order("recorded_at", desc=True).limit(50).execute()

    return {"data": result.data or []}


@router.get("/api/usage/me")
async def get_my_usage(authorization: Optional[str] = Header(None)):
    """Get usage metrics for the current user's org."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    db = get_admin_client()

    result = db.table("product_usage").select(
        "*, products(nome, slug)"
    ).eq("org_id", org_id).order("recorded_at", desc=True).limit(50).execute()

    return {"data": result.data or []}


@router.post("/api/admin/usage/snapshot")
async def trigger_snapshot(authorization: Optional[str] = Header(None)):
    """Trigger a manual usage snapshot (admin only)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    try:
        db.rpc("snapshot_product_usage").execute()
        return {"status": "ok", "message": "Snapshot de uso executado com sucesso"}
    except Exception as e:
        logger.error(f"Failed to run usage snapshot: {e}")
        raise HTTPException(status_code=500, detail="Erro ao executar snapshot de uso")
