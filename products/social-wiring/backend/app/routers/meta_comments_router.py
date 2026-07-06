"""Meta comment moderation — account-scoped (Wave 3).

Endpoint shapes below are pinned to what Slice 3B (frontend, already
built) calls — reconciled with the tech-lead mid-flight, superseding the
earlier draft's unified ``action``-field POST + path-param DELETE:

    GET    /api/meta/instagram/comments?account_id=&media_id=
    POST   /api/meta/instagram/comments        {media_id, message, parent_comment_id?}
    POST   /api/meta/instagram/comments/hide   {comment_id, hide}
    DELETE /api/meta/instagram/comments?account_id=&comment_id=

    GET    /api/meta/facebook/comments?account_id=&post_id=
    POST   /api/meta/facebook/comments         {post_id, message}
    POST   /api/meta/facebook/comments/hide    {comment_id, hide}
    DELETE /api/meta/facebook/comments?account_id=&comment_id=

IG's POST body creates a NEW top-level comment on ``media_id`` when
``parent_comment_id`` is absent (seed's ``create_instagram_comment`` —
Graph's ``POST /{media}/comments`` edge), or replies to
``parent_comment_id`` when present (``reply_instagram_comment`` —
``POST /{comment}/replies``, a DIFFERENT edge — Graph does not unify
these). FB's POST body has no parent id — per this contract FB comment
creation is always top-level (``create_facebook_comment`` — ``POST
/{post}/comments``); ``reply_facebook_comment`` (threaded reply to an
existing FB comment) stays available on the adapter but is not wired to
a route here (no FE need for it under this contract).

Every write routes ``MetaGraphError`` through the uniform Wave 3 gate
(``handle_meta_graph_error``) — comment moderation needs
``instagram_manage_comments`` / ``pages_manage_engagement``, both App
Review gated in production."""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel

from app.routers._meta_common import get_account_adapter, handle_meta_graph_error
from app.services.meta import MetaAdapter, MetaGraphError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta-comments"])


# ─── Response shapes ────────────────────────────────────────────────────
class MetaCommentOut(BaseModel):
    id: str
    text: str | None = None
    author: str | None = None
    author_id: str | None = None
    created_at: datetime | None = None
    like_count: int = 0
    hidden: bool = False
    parent_id: str | None = None


class MetaCommentsListOut(BaseModel):
    comments: list[MetaCommentOut]


class MetaHideCommentIn(StrictHttpModel):
    comment_id: str
    hide: bool = True


class MetaHideCommentOut(BaseModel):
    comment_id: str
    hidden: bool


class MetaCommentDeleteOut(BaseModel):
    comment_id: str
    deleted: bool = True


class InstagramCommentCreateIn(StrictHttpModel):
    media_id: str
    message: str = Field(..., min_length=1)
    parent_comment_id: str | None = None


class FacebookCommentCreateIn(StrictHttpModel):
    post_id: str
    message: str = Field(..., min_length=1)


def _ig_comment_out(comment) -> MetaCommentOut:
    return MetaCommentOut(
        id=comment.id,
        text=comment.text,
        author=comment.username,
        created_at=comment.timestamp,
        like_count=comment.like_count,
        hidden=comment.hidden,
        parent_id=comment.parent_id,
    )


def _fb_comment_out(comment) -> MetaCommentOut:
    return MetaCommentOut(
        id=comment.id,
        text=comment.message,
        author=comment.from_name,
        author_id=comment.from_id,
        created_at=comment.created_time,
        like_count=comment.like_count,
        hidden=comment.is_hidden,
        parent_id=comment.parent_id,
    )


# ─── Instagram ───────────────────────────────────────────────────────────
@router.get("/api/meta/instagram/comments", response_model=MetaCommentsListOut)
def list_instagram_comments(
    media_id: str = Query(...),
    limit: int = Query(default=25, ge=1, le=100),
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        comments = adapter.list_instagram_comments(media_id, limit)
    except MetaGraphError as exc:
        logger.warning("meta comments: ig list failed for %s: %s", media_id, exc)
        return handle_meta_graph_error(exc)
    return MetaCommentsListOut(comments=[_ig_comment_out(c) for c in comments])


@router.post("/api/meta/instagram/comments", response_model=MetaCommentOut)
def create_instagram_comment(
    payload: InstagramCommentCreateIn,
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        if payload.parent_comment_id:
            comment = adapter.reply_instagram_comment(
                payload.parent_comment_id, payload.message
            )
        else:
            comment = adapter.create_instagram_comment(
                payload.media_id, payload.message
            )
    except MetaGraphError as exc:
        logger.warning(
            "meta comments: ig create/reply failed for %s: %s",
            payload.media_id, exc,
        )
        return handle_meta_graph_error(exc)
    return _ig_comment_out(comment)


@router.post("/api/meta/instagram/comments/hide", response_model=MetaHideCommentOut)
def hide_instagram_comment(
    payload: MetaHideCommentIn,
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        adapter.hide_instagram_comment(payload.comment_id, hide=payload.hide)
    except MetaGraphError as exc:
        logger.warning(
            "meta comments: ig hide failed for %s: %s", payload.comment_id, exc
        )
        return handle_meta_graph_error(exc)
    return MetaHideCommentOut(comment_id=payload.comment_id, hidden=payload.hide)


@router.delete("/api/meta/instagram/comments", response_model=MetaCommentDeleteOut)
def delete_instagram_comment(
    comment_id: str = Query(...),
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        adapter.delete_instagram_comment(comment_id)
    except MetaGraphError as exc:
        logger.warning("meta comments: ig delete failed for %s: %s", comment_id, exc)
        return handle_meta_graph_error(exc)
    return MetaCommentDeleteOut(comment_id=comment_id)


# ─── Facebook ────────────────────────────────────────────────────────────
@router.get("/api/meta/facebook/comments", response_model=MetaCommentsListOut)
def list_facebook_comments(
    post_id: str = Query(...),
    limit: int = Query(default=25, ge=1, le=100),
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        comments = adapter.list_facebook_comments(post_id, limit)
    except MetaGraphError as exc:
        logger.warning("meta comments: fb list failed for %s: %s", post_id, exc)
        return handle_meta_graph_error(exc)
    return MetaCommentsListOut(comments=[_fb_comment_out(c) for c in comments])


@router.post("/api/meta/facebook/comments", response_model=MetaCommentOut)
def create_facebook_comment(
    payload: FacebookCommentCreateIn,
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        comment = adapter.create_facebook_comment(payload.post_id, payload.message)
    except MetaGraphError as exc:
        logger.warning(
            "meta comments: fb create failed for %s: %s", payload.post_id, exc
        )
        return handle_meta_graph_error(exc)
    return _fb_comment_out(comment)


@router.post("/api/meta/facebook/comments/hide", response_model=MetaHideCommentOut)
def hide_facebook_comment(
    payload: MetaHideCommentIn,
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        adapter.hide_facebook_comment(payload.comment_id, hide=payload.hide)
    except MetaGraphError as exc:
        logger.warning(
            "meta comments: fb hide failed for %s: %s", payload.comment_id, exc
        )
        return handle_meta_graph_error(exc)
    return MetaHideCommentOut(comment_id=payload.comment_id, hidden=payload.hide)


@router.delete("/api/meta/facebook/comments", response_model=MetaCommentDeleteOut)
def delete_facebook_comment(
    comment_id: str = Query(...),
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        adapter.delete_facebook_comment(comment_id)
    except MetaGraphError as exc:
        logger.warning("meta comments: fb delete failed for %s: %s", comment_id, exc)
        return handle_meta_graph_error(exc)
    return MetaCommentDeleteOut(comment_id=comment_id)


__all__ = ["router"]
