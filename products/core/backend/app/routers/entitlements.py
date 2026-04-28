"""
Entitlements Router — Feature gating and plan limit checks.

GET /api/entitlements               — Get all entitlements for the current user's org
GET /api/entitlements/check/{feature} — Check if a specific feature is available
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException

from app.dependencies import get_current_user, get_org_id
from app.services.entitlements import check_feature, get_org_entitlements

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/entitlements", tags=["Entitlements"])


@router.get("")
async def listar_entitlements(authorization: Optional[str] = Header(None)):
    """Get all entitlements for the current user's organization."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)

    entitlements = await get_org_entitlements(org_id)
    return {"data": entitlements}


@router.get("/check/{feature}")
async def verificar_feature(feature: str, authorization: Optional[str] = Header(None)):
    """Check if a specific feature is available for the current user's org."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)

    has_feature = await check_feature(org_id, feature)
    return {
        "feature": feature,
        "available": has_feature,
        "org_id": org_id,
    }
