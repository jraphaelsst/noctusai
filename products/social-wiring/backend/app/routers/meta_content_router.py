"""Meta content publishing + FB post listing — account-scoped (Wave 3).

``POST /api/meta/instagram/publish`` (``kind`` = media | carousel | reel
| story), ``POST /api/meta/facebook/publish`` (``kind`` = post | photo |
video), and ``GET /api/meta/facebook/posts?account_id=&page_id=`` (Page
posts list — ``adapter.list_facebook_posts(page_id)``; a read, added on
tech-lead reconciliation with the already-built Slice 3B frontend). All
resolve the adapter via ``Depends(get_account_adapter)``; the two writes
route ``MetaGraphError`` through the uniform Wave 3 gate
(``handle_meta_graph_error``): a write scope pending Meta App Review is
the expected, common case here (publishing needs
``instagram_content_publish`` / ``pages_manage_posts`` — App Review
gated in production) — 200 structured, never a 500; any other Graph
failure → 502 structured.

Instagram's ``ig_user_id`` resolves from the account (no caller-supplied
id — mirrors ``meta_insights_router``); Facebook's ``page_id`` is
caller-supplied (a connection can manage MULTIPLE Pages, unlike the
"exactly one linked IG account" assumption)."""
from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from noctusai_lib.api import StrictHttpModel

from app.routers._meta_common import (
    get_account_adapter,
    handle_meta_graph_error,
    resolve_primary_ig_user_id,
)
from app.services.meta import MetaAdapter, MetaGraphError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta-content"])


# ─── Request/response shapes ─────────────────────────────────────────────
class InstagramPublishIn(StrictHttpModel):
    kind: Literal["media", "carousel", "reel", "story"]
    media_url: str | None = None
    media_urls: list[str] | None = None
    caption: str | None = None
    is_video: bool = False  # story only — image vs. video story container


class FacebookPublishIn(StrictHttpModel):
    kind: Literal["post", "photo", "video"]
    page_id: str
    message: str | None = None
    link: str | None = None
    photo_url: str | None = None
    video_url: str | None = None
    as_reel: bool = False  # video only


class MetaPublishMediaOut(BaseModel):
    id: str
    ig_user_id: str | None = None
    container_id: str | None = None
    permalink: str | None = None
    processing_duration_ms: int | None = None


class MetaPublishPostOut(BaseModel):
    id: str
    page_id: str | None = None
    permalink: str | None = None
    processing_duration_ms: int | None = None


# ─── POST /instagram/publish ──────────────────────────────────────────────
@router.post("/api/meta/instagram/publish", response_model=MetaPublishMediaOut)
def publish_instagram(
    payload: InstagramPublishIn,
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        ig_user_id = resolve_primary_ig_user_id(adapter)

        if payload.kind == "media":
            if not payload.media_url:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="media_url is required for kind=media",
                )
            published = adapter.publish_instagram_media(
                ig_user_id, payload.media_url, caption=payload.caption
            )
        elif payload.kind == "carousel":
            if not payload.media_urls or len(payload.media_urls) < 2:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="media_urls needs at least 2 images for kind=carousel",
                )
            published = adapter.publish_instagram_carousel(
                ig_user_id, payload.media_urls, caption=payload.caption
            )
        elif payload.kind == "reel":
            if not payload.media_url:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="media_url is required for kind=reel",
                )
            published = adapter.publish_instagram_reel(
                ig_user_id, payload.media_url, caption=payload.caption
            )
        else:  # story
            if not payload.media_url:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="media_url is required for kind=story",
                )
            published = adapter.publish_instagram_story(
                ig_user_id, payload.media_url, is_video=payload.is_video
            )
    except MetaGraphError as exc:
        logger.warning("meta content: instagram publish failed: %s", exc)
        return handle_meta_graph_error(exc)

    return MetaPublishMediaOut(
        id=published.id,
        ig_user_id=published.ig_user_id,
        container_id=published.container_id,
        permalink=published.permalink,
        processing_duration_ms=published.processing_duration_ms,
    )


# ─── POST /facebook/publish ───────────────────────────────────────────────
@router.post("/api/meta/facebook/publish", response_model=MetaPublishPostOut)
def publish_facebook(
    payload: FacebookPublishIn,
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        if payload.kind == "post":
            if not payload.message:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="message is required for kind=post",
                )
            published = adapter.publish_facebook_post(
                payload.page_id, payload.message, link=payload.link
            )
        elif payload.kind == "photo":
            if not payload.photo_url:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="photo_url is required for kind=photo",
                )
            published = adapter.publish_facebook_post(
                payload.page_id,
                payload.message or "",
                photo_url=payload.photo_url,
            )
        else:  # video
            if not payload.video_url:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="video_url is required for kind=video",
                )
            published = adapter.publish_facebook_video(
                payload.page_id,
                payload.video_url,
                description=payload.message,
                as_reel=payload.as_reel,
            )
    except MetaGraphError as exc:
        logger.warning("meta content: facebook publish failed: %s", exc)
        return handle_meta_graph_error(exc)

    return MetaPublishPostOut(
        id=published.id,
        page_id=published.page_id,
        permalink=published.permalink_url,
        processing_duration_ms=published.processing_duration_ms,
    )


# ─── GET /facebook/posts ──────────────────────────────────────────────────
class FacebookPostOut(BaseModel):
    id: str
    message: str | None = None
    created_time: str | None = None
    permalink_url: str | None = None
    full_picture: str | None = None
    likes: int = 0
    comments: int = 0
    shares: int = 0


class FacebookPostsListOut(BaseModel):
    posts: list[FacebookPostOut]


def _post_out(post: Any) -> FacebookPostOut:
    return FacebookPostOut(
        id=post.id,
        message=post.message,
        created_time=post.created_time.isoformat() if post.created_time else None,
        permalink_url=post.permalink_url,
        full_picture=post.full_picture,
        likes=post.likes,
        comments=post.comments,
        shares=post.shares,
    )


@router.get("/api/meta/facebook/posts", response_model=FacebookPostsListOut)
def list_facebook_posts(
    page_id: str = Query(...),
    limit: int = Query(default=25, ge=1, le=100),
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        posts = adapter.list_facebook_posts(page_id, limit)
    except MetaGraphError as exc:
        logger.warning("meta content: facebook posts list failed for %s: %s", page_id, exc)
        return handle_meta_graph_error(exc)
    return FacebookPostsListOut(posts=[_post_out(p) for p in posts])


__all__ = ["router"]
