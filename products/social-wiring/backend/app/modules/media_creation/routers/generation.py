"""Generation endpoints — the 3-stage LLM pipeline (storyboard / prompts / copy).

A 4th endpoint (``/render``) returns a typed ``gate=image_generation_not_configured``
signal per gated-capability-honesty until the ``image-gen-seed-adapter``
project ships ``noctusai_lib.integrations.image_gen``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org, get_org_id
from app.modules.media_creation.services.generation_service import (
    GenerationError,
    GenerationService,
)
from app.modules.media_creation.services.post_service import PostService

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/media-creation/posts",
    tags=["Media Creation — Generation"],
)


def _post_svc(user) -> PostService:
    return PostService(get_admin_client(), get_org_id(user))


def _gen_svc(user) -> GenerationService:
    return GenerationService(get_admin_client(), get_org_id(user))


def _require_post(user, post_id: str) -> dict:
    post = _post_svc(user).get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post não encontrado")
    return post


@router.post("/{post_id}/generate/storyboard")
async def generate_storyboard(post_id: str, auth=Depends(get_current_user_org)):
    user, _, _ = auth
    post = _require_post(user, post_id)
    try:
        data = await _gen_svc(user).generate_storyboard(post)
    except GenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return success_response(data)


@router.post("/{post_id}/generate/prompts")
async def generate_prompts(post_id: str, auth=Depends(get_current_user_org)):
    user, _, _ = auth
    post = _require_post(user, post_id)
    try:
        data = await _gen_svc(user).generate_image_prompts(post)
    except GenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return success_response(data)


@router.post("/{post_id}/generate/copy")
async def generate_copy(post_id: str, auth=Depends(get_current_user_org)):
    user, _, _ = auth
    post = _require_post(user, post_id)
    try:
        data = await _gen_svc(user).generate_copy(post)
    except GenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return success_response(data)


@router.post("/{post_id}/render")
async def render_post(post_id: str, auth=Depends(get_current_user_org)):
    """Typed never-faked gate signal until the image-gen seed adapter ships.

    Per ``feedback_gated_capability_honesty``: the endpoint EXISTS (so the
    FE can call it unconditionally and react to the typed gate response),
    rather than hiding the capability. When ``noctusai_lib.integrations.
    image_gen`` ships, this handler will flip to real rendering without an
    FE contract change.
    """
    user, _, _ = auth
    _require_post(user, post_id)  # 404 if post doesn't belong to org
    return {
        "ok": False,
        "gate": "image_generation_not_configured",
        "message": (
            "A geração de imagens será habilitada em uma fase posterior. "
            "Por enquanto, copie os prompts gerados e cole no GalilAI, "
            "Nano Banana ou Midjourney."
        ),
        "renderers_supported_when_enabled": ["nano_banana", "galilai", "midjourney"],
    }
