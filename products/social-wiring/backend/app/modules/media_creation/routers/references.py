"""Brand-reference CRUD endpoints (nested under a brand kit).

URL-only references are created here (``POST /brand-kits/{id}/references``);
UPLOADED assets (logos, post models, fonts) are created through
``POST /branding/{id}/assets``. Deleting a reference is one route for both —
it also removes the blob of an uploaded asset.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.deps import get_branding_storage
from app.modules.media_creation.schemas.references import ReferenceCreate
from app.modules.media_creation.services.branding_service import (
    BrandingError,
    BrandingService,
)
from app.modules.media_creation.services.reference_service import ReferenceService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media-creation", tags=["Media Creation — References"])


def _svc(org_id) -> ReferenceService:
    return ReferenceService(get_admin_client(), org_id)


@router.get("/brand-kits/{kit_id}/references")
async def list_references(kit_id: str, auth=Depends(get_current_user_org)):
    user, _, org_id = auth
    return success_response(_svc(org_id).list_references(kit_id))


@router.post("/brand-kits/{kit_id}/references", status_code=201)
async def create_reference(
    kit_id: str, body: ReferenceCreate, auth=Depends(get_current_user_org)
):
    user, _, org_id = auth
    result = _svc(org_id).create_reference(kit_id, body.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Kit de marca não encontrado")
    return success_response(result)


@router.delete("/references/{reference_id}")
async def delete_reference(
    reference_id: str,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_branding_storage),
):
    user, _, org_id = auth
    branding = BrandingService(get_admin_client(), org_id, storage)
    try:
        await branding.delete_asset(reference_id)
    except BrandingError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"ok": True, "message": "Referência removida"}
