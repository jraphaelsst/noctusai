"""Brand-reference CRUD endpoints (nested under a brand kit)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org, get_org_id
from app.modules.media_creation.schemas.references import ReferenceCreate
from app.modules.media_creation.services.reference_service import ReferenceService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media-creation", tags=["Media Creation — References"])


def _svc(user) -> ReferenceService:
    return ReferenceService(get_admin_client(), get_org_id(user))


@router.get("/brand-kits/{kit_id}/references")
async def list_references(kit_id: str, auth=Depends(get_current_user_org)):
    user, _, _ = auth
    return success_response(_svc(user).list_references(kit_id))


@router.post("/brand-kits/{kit_id}/references", status_code=201)
async def create_reference(
    kit_id: str, body: ReferenceCreate, auth=Depends(get_current_user_org)
):
    user, _, _ = auth
    result = _svc(user).create_reference(kit_id, body.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Kit de marca não encontrado")
    return success_response(result)


@router.delete("/references/{reference_id}")
async def delete_reference(reference_id: str, auth=Depends(get_current_user_org)):
    user, _, _ = auth
    _svc(user).delete_reference(reference_id)
    return {"ok": True, "message": "Referência removida"}
