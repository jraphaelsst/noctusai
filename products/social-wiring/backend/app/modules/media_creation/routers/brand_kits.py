"""Brand-kit CRUD endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org, get_org_id
from app.modules.media_creation.schemas.brand_kits import BrandKitCreate, BrandKitUpdate
from app.modules.media_creation.services.brand_kit_service import BrandKitService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media-creation/brand-kits", tags=["Media Creation — Brand Kits"])


def _svc(user) -> BrandKitService:
    return BrandKitService(get_admin_client(), get_org_id(user))


@router.get("")
async def list_brand_kits(auth=Depends(get_current_user_org)):
    user, _, _ = auth
    return success_response(_svc(user).list_kits())


@router.post("", status_code=201)
async def create_brand_kit(body: BrandKitCreate, auth=Depends(get_current_user_org)):
    user, _, _ = auth
    result = _svc(user).create_kit(body.model_dump(), str(user.id))
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao criar kit de marca")
    return success_response(result)


@router.get("/{kit_id}")
async def get_brand_kit(kit_id: str, auth=Depends(get_current_user_org)):
    user, _, _ = auth
    result = _svc(user).get_kit(kit_id)
    if not result:
        raise HTTPException(status_code=404, detail="Kit de marca não encontrado")
    return success_response(result)


@router.patch("/{kit_id}")
async def update_brand_kit(
    kit_id: str, body: BrandKitUpdate, auth=Depends(get_current_user_org)
):
    user, _, _ = auth
    result = _svc(user).update_kit(kit_id, body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Kit de marca não encontrado")
    return success_response(result)


@router.delete("/{kit_id}")
async def delete_brand_kit(kit_id: str, auth=Depends(get_current_user_org)):
    user, _, _ = auth
    if not _svc(user).delete_kit(kit_id):
        raise HTTPException(
            status_code=400,
            detail="Kit em uso — exclua os posts antes de remover este kit",
        )
    return {"ok": True, "message": "Kit removido"}
