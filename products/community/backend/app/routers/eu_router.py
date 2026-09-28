"""`GET /api/eu` router — contract §Identity, slice BE-A.

Base auth (`get_any_org_user`) — NOT the staff gate `get_current_user_org`
(which 403s a `membro`) and NOT `get_membro_context` (which 403s anyone
without a linked `membros` row): "any authenticated org user".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import coerce_org_uuid, get_admin_client, get_any_org_user, get_community_role
from app.schemas.eu import EuOut
from app.services.eu_service import build_eu

router = APIRouter(prefix="/api/eu", tags=["eu"])


@router.get("", response_model=EuOut)
async def get_eu(auth: tuple = Depends(get_any_org_user)) -> EuOut:
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    papel = get_community_role(user)
    client = get_admin_client()
    return EuOut(**build_eu(client, user=user, org_id=org_id, papel=papel))
