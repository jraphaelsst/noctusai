"""Generation endpoints — the 4-stage LLM + image-gen pipeline.

- ``/generate/storyboard`` · ``/generate/prompts`` · ``/generate/copy`` —
  LLM stages.
- ``/render`` — image-generation stage, backed by the
  ``noctusai_lib.integrations.image_gen`` seed adapter. When the org has
  no Gemini key configured, the adapter resolves to ``FakeImageGenAdapter``
  and the response carries ``configured=False`` + ``fake-image-gen.noctusai.local``
  URLs — the loud "not configured" signal per
  ``feedback_gated_capability_honesty``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org, get_org_id
from app.modules.media_creation.services.generation_service import (
    GenerationError,
    GenerationService,
)
from app.modules.media_creation.services.post_service import PostService
from app.modules.media_creation.services.publish_service import (
    PublishError,
    PublishService,
)


class RenderRequest(BaseModel):
    renderer: str = "nano_banana"
    # "raster" (default) → AI image per slide via image-gen; "svg" →
    # deterministic brand-locked SVG slides rasterized via the seed svg_render.
    mode: str = "raster"
    # Optional design-token variant override for svg mode (premium/educational);
    # defaults to the post's own variant.
    variant: str | None = None


class PublishRequest(BaseModel):
    target: str = "instagram_carousel"
    destination_id: str

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/media-creation/posts",
    tags=["Media Creation — Generation"],
)


def _post_svc(user) -> PostService:
    return PostService(get_admin_client(), get_org_id(user))


def _gen_svc(user) -> GenerationService:
    return GenerationService(get_admin_client(), get_org_id(user))


def _publish_svc(user) -> PublishService:
    return PublishService(get_admin_client(), get_org_id(user))


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
async def render_post(
    post_id: str,
    body: RenderRequest | None = None,
    auth=Depends(get_current_user_org),
):
    """Render the post's slides.

    ``mode="raster"`` (default) — one AI image per slide via the seed
    image-gen adapter (Gemini "Nano Banana"). Returns ``configured`` so the
    FE can show a "configure Gemini key" prompt when the Fake fired.

    ``mode="svg"`` — deterministic, brand-locked SVG slides (locked palette /
    typography / layout from the brand kit's design tokens; AI not used for
    text/layout) rasterized via the seed ``svg_render`` primitive.
    """
    user, _, _ = auth
    post = _require_post(user, post_id)
    renderer = (body.renderer if body else "nano_banana") or "nano_banana"
    mode = (body.mode if body else "raster") or "raster"
    variant = body.variant if body else None
    try:
        data = _gen_svc(user).render_post(
            post, renderer=renderer, mode=mode, variant=variant
        )
    except GenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return success_response(data)


@router.post("/{post_id}/publish")
async def publish_post(
    post_id: str,
    body: PublishRequest,
    auth=Depends(get_current_user_org),
):
    """Publish a rendered post to Meta (IG carousel / IG single / FB photo).

    Resolves the seed ``MetaAdapter`` — if no ``META_SYSTEM_USER_TOKEN`` is
    configured the Fake fires (deterministic, no network). The Fake never
    raises ``requires_app_review`` so dev/test paths complete; production
    only surfaces 422 + ``meta_scope_pending_app_review`` when the App
    Review gate is still pending.
    """
    user, _, _ = auth
    post = _require_post(user, post_id)
    try:
        data = _publish_svc(user).publish_post(
            post,
            target=body.target,
            destination_id=body.destination_id,
        )
    except PublishError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return success_response(data)
