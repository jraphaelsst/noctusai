"""Graph API JSON body → dataclass mappers.

Centralised so the OAuth adapter and the Fake adapter return identical
dataclass shapes. Insights mapping is its own helper because every
Graph insight response wraps values inside a list of dicts with a
different shape than the entity endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.meta.types import (
    FacebookPage,
    FacebookPost,
    InstagramAccount,
    InstagramMedia,
    PostInsights,
)


# Default fields we ask Graph API for. Each ``_FIELDS`` constant maps
# to the ``fields`` querystring param on the corresponding endpoint.
PAGE_FIELDS = "id,name,category,access_token,fan_count,followers_count,link,tasks"

POST_FIELDS = (
    "id,message,created_time,permalink_url,full_picture,"
    "attachments{title,description,type,media_type,unshimmed_url},"
    "likes.summary(true).limit(0),"
    "comments.summary(true).limit(0),"
    "shares"
)

IG_ACCOUNT_FIELDS = (
    "id,username,name,profile_picture_url,followers_count,follows_count,"
    "media_count,biography,website"
)

IG_MEDIA_FIELDS = (
    "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp,"
    "like_count,comments_count"
)

# Default insight metrics we ask for per surface. Both lists are
# conservative — adding more is cheap (one more comma in the
# ``metric`` querystring) but each metric counts toward the Graph
# API quota.
FB_POST_INSIGHT_METRICS = [
    "post_impressions",
    "post_impressions_unique",
    "post_engaged_users",
    "post_clicks",
    "post_reactions_like_total",
    "post_reactions_love_total",
    "post_reactions_wow_total",
    "post_reactions_haha_total",
    "post_reactions_sorry_total",
    "post_reactions_anger_total",
]

IG_MEDIA_INSIGHT_METRICS = [
    "impressions",
    "reach",
    "engagement",
    "saved",
    "video_views",
]


def parse_graph_datetime(value: Any) -> datetime | None:
    """Graph API returns ISO-8601 with timezone (``2026-01-15T12:34:56+0000``).
    Python's ``fromisoformat`` accepts that since 3.11 — except for the
    ``+0000`` form, which we normalize to ``+00:00``.
    """
    if not isinstance(value, str):
        return None
    normalized = value
    if normalized.endswith("+0000"):
        normalized = normalized[:-5] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def page_body_to_facebook_page(body: dict[str, Any]) -> FacebookPage:
    return FacebookPage(
        page_id=body["id"],
        name=body.get("name", ""),
        category=body.get("category"),
        access_token=body.get("access_token", ""),
        fan_count=_parse_int(body.get("fan_count")),
        followers_count=_parse_int(body.get("followers_count")),
        link=body.get("link"),
        tasks=list(body.get("tasks") or []),
        raw=body,
    )


def post_body_to_facebook_post(body: dict[str, Any], *, page_id: str) -> FacebookPost:
    """Map a single Facebook Page post.

    Likes/comments/shares are returned via the ``summary`` extension on
    the edge — ``likes.summary(true)`` makes the API include a
    ``summary.total_count`` instead of the full edge body, which is the
    only count we care about and is much cheaper.
    """
    likes = (body.get("likes") or {}).get("summary") or {}
    comments = (body.get("comments") or {}).get("summary") or {}
    shares = body.get("shares") or {}

    attachments = []
    for att in ((body.get("attachments") or {}).get("data") or []):
        label = att.get("title") or att.get("description") or att.get("type") or ""
        if label:
            attachments.append(label)

    return FacebookPost(
        id=body["id"],
        page_id=page_id,
        message=body.get("message"),
        created_at=parse_graph_datetime(body.get("created_time")),
        permalink_url=body.get("permalink_url"),
        full_picture=body.get("full_picture"),
        attachments_summary=attachments,
        likes_count=_parse_int(likes.get("total_count")),
        comments_count=_parse_int(comments.get("total_count")),
        shares_count=_parse_int(shares.get("count")),
        raw=body,
    )


def ig_account_body_to_instagram_account(
    body: dict[str, Any],
    *,
    linked_page_id: str | None = None,
) -> InstagramAccount:
    return InstagramAccount(
        ig_user_id=body["id"],
        username=body.get("username", ""),
        name=body.get("name"),
        profile_picture_url=body.get("profile_picture_url"),
        followers_count=_parse_int(body.get("followers_count")),
        follows_count=_parse_int(body.get("follows_count")),
        media_count=_parse_int(body.get("media_count")),
        biography=body.get("biography"),
        website=body.get("website"),
        linked_page_id=linked_page_id,
        raw=body,
    )


def media_body_to_instagram_media(
    body: dict[str, Any],
    *,
    ig_user_id: str,
) -> InstagramMedia:
    return InstagramMedia(
        id=body["id"],
        ig_user_id=ig_user_id,
        caption=body.get("caption"),
        media_type=body.get("media_type") or "",
        media_url=body.get("media_url"),
        permalink=body.get("permalink"),
        thumbnail_url=body.get("thumbnail_url"),
        timestamp=parse_graph_datetime(body.get("timestamp")),
        like_count=_parse_int(body.get("like_count")),
        comments_count=_parse_int(body.get("comments_count")),
        raw=body,
    )


def insight_body_to_post_insights(
    body: dict[str, Any],
    *,
    object_id: str,
) -> PostInsights:
    """Map an insight body like::

        {"data": [
          {"name": "post_impressions",
           "period": "lifetime",
           "values": [{"value": 1234}]},
          ...
        ]}

    into a flat ``{metric_name: value}`` dict the chatbot can quote.
    """
    metrics: dict[str, int | float] = {}
    period = "lifetime"
    for row in body.get("data") or []:
        name = row.get("name")
        if not name:
            continue
        period = row.get("period") or period
        values = row.get("values") or []
        if not values:
            metrics[name] = 0
            continue
        # For most engagement metrics there's a single value with no
        # end_time; for time-bucketed metrics we just take the latest
        # bucket's value (Graph orders ascending, last is most recent).
        raw_value = values[-1].get("value", 0)
        if isinstance(raw_value, dict):
            # Some metrics (reactions breakdown) return dicts —
            # flatten by summing.
            try:
                raw_value = sum(int(v) for v in raw_value.values())
            except (TypeError, ValueError):
                raw_value = 0
        try:
            metrics[name] = int(raw_value)
        except (TypeError, ValueError):
            try:
                metrics[name] = float(raw_value)
            except (TypeError, ValueError):
                metrics[name] = 0
    return PostInsights(
        object_id=object_id,
        period=period,
        metrics=metrics,
        raw=body,
    )


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
