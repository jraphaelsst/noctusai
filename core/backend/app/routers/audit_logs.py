"""
Audit Logs Router — View audit trail for security and compliance.

GET /api/audit-logs          — List audit logs for the current user's org (paginated)
GET /api/admin/audit-logs    — List all audit logs across platform (admin only, paginated)

Query params: page, page_size, action (filter), resource_type (filter)
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Audit Logs"])


@router.get("/api/audit-logs")
async def listar_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: Optional[str] = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(None),
):
    """List audit logs for the current user's organization (paginated)."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Get user's org_id
    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data or not profile.data.get("org_id"):
        raise HTTPException(status_code=404, detail="Perfil ou organização não encontrada")

    org_id = profile.data["org_id"]
    offset = (page - 1) * page_size

    # Build query with filters
    count_query = db.table("audit_logs").select("id", count="exact").eq("org_id", org_id)
    data_query = db.table("audit_logs").select("*").eq("org_id", org_id)

    if action:
        count_query = count_query.eq("action", action)
        data_query = data_query.eq("action", action)
    if resource_type:
        count_query = count_query.eq("resource_type", resource_type)
        data_query = data_query.eq("resource_type", resource_type)

    # Total count
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(count_result.data or [])

    # Paginated data
    result = data_query.order(
        "created_at", desc=True
    ).range(offset, offset + page_size - 1).execute()

    return {
        "data": result.data or [],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/api/admin/audit-logs")
async def admin_listar_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    action: Optional[str] = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(None),
):
    """List all audit logs across the platform (admin only, paginated)."""
    await get_current_admin(authorization)
    db = get_admin_client()

    offset = (page - 1) * page_size

    # Build query with optional filters
    count_query = db.table("audit_logs").select("id", count="exact")
    data_query = db.table("audit_logs").select(
        "*, noctus_users(id, nome, email), organizations(id, nome)"
    )

    if action:
        count_query = count_query.eq("action", action)
        data_query = data_query.eq("action", action)
    if resource_type:
        count_query = count_query.eq("resource_type", resource_type)
        data_query = data_query.eq("resource_type", resource_type)

    # Total count
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(count_result.data or [])

    # Paginated data with user and org info
    result = data_query.order(
        "created_at", desc=True
    ).range(offset, offset + page_size - 1).execute()

    return {
        "data": result.data or [],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
