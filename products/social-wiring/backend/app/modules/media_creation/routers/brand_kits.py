"""Brand-kit CRUD endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.deps import get_branding_storage
from app.modules.media_creation.schemas.brand_kits import BrandKitCreate, BrandKitUpdate
from app.modules.media_creation.services.brand_kit_service import BrandKitService
from app.modules.media_creation.services.branding_service import BrandingError, BrandingService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media-creation/brand-kits", tags=["Media Creation — Brand Kits"])


def _svc(org_id) -> BrandKitService:
    return BrandKitService(get_admin_client(), org_id)


@router.get("")
async def list_brand_kits(auth=Depends(get_current_user_org)):
    user, _, org_id = auth
    return success_response(_svc(org_id).list_kits())


@router.post("", status_code=201)
async def create_brand_kit(body: BrandKitCreate, auth=Depends(get_current_user_org)):
    user, _, org_id = auth
    result = _svc(org_id).create_kit(body.model_dump(), str(user.id))
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao criar kit de marca")
    return success_response(result)


@router.get("/{kit_id}")
async def get_brand_kit(kit_id: str, auth=Depends(get_current_user_org)):
    user, _, org_id = auth
    result = _svc(org_id).get_kit(kit_id)
    if not result:
        raise HTTPException(status_code=404, detail="Kit de marca não encontrado")
    return success_response(result)


@router.patch("/{kit_id}")
async def update_brand_kit(
    kit_id: str, body: BrandKitUpdate, auth=Depends(get_current_user_org)
):
    user, _, org_id = auth
    result = _svc(org_id).update_kit(kit_id, body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Kit de marca não encontrado")
    return success_response(result)


@router.delete("/{kit_id}")
async def delete_brand_kit(
    kit_id: str,
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_branding_storage),
):
    # One delete path for kits and brandings: it also removes the blobs of
    # uploaded assets and protects the Branding Template.
    user, _, org_id = auth
    try:
        await BrandingService(get_admin_client(), org_id, storage).delete(kit_id)
    except BrandingError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"ok": True, "message": "Kit removido"}
