"""Post CRUD endpoints."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org, get_org_id
from app.modules.media_creation.schemas.posts import PostCreate, PostUpdate
from app.modules.media_creation.services.post_service import PostService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media-creation/posts", tags=["Media Creation — Posts"])


def _svc(user) -> PostService:
    return PostService(get_admin_client(), get_org_id(user))


@router.get("")
async def list_posts(
    auth=Depends(get_current_user_org),
    status: Optional[str] = Query(None),
    brand_kit_id: Optional[str] = Query(None),
):
    user, _, _ = auth
    return success_response(_svc(user).list_posts(status=status, brand_kit_id=brand_kit_id))


@router.post("", status_code=201)
async def create_post(body: PostCreate, auth=Depends(get_current_user_org)):
    user, _, _ = auth
    result = _svc(user).create_post(body.model_dump(), str(user.id))
    if not result:
        raise HTTPException(status_code=400, detail="Kit de marca inválido")
    return success_response(result)


@router.get("/{post_id}")
async def get_post(post_id: str, auth=Depends(get_current_user_org)):
    user, _, _ = auth
    result = _svc(user).get_post_detail(post_id)
    if not result:
        raise HTTPException(status_code=404, detail="Post não encontrado")
    return success_response(result)


@router.patch("/{post_id}")
async def update_post(
    post_id: str, body: PostUpdate, auth=Depends(get_current_user_org)
):
    user, _, _ = auth
    result = _svc(user).update_post(post_id, body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Post não encontrado")
    return success_response(result)


@router.delete("/{post_id}")
async def delete_post(post_id: str, auth=Depends(get_current_user_org)):
    user, _, _ = auth
    if not _svc(user).delete_post(post_id):
        raise HTTPException(
            status_code=400,
            detail="Apenas posts em rascunho ou prontos podem ser excluídos",
        )
    return {"ok": True, "message": "Post excluído"}
