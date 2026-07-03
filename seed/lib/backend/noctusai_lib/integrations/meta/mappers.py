"""Graph JSON → dataclass mappers + default field/metric constants.

Pure functions only — no IO. Mirrors the calendar/maps mapper module
posture (testable in isolation, no network). The `FIELDS` constants
encode the `.summary(true).limit(0)` bandwidth trick: ask Graph for an
edge's `summary.total_count` without expanding the edge body (a post
with 5,000 likes returns ~80 bytes instead of ~200KB).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from noctusai_lib.integrations.meta.types import (
    FacebookPage,
    FacebookPost,
    InstagramAccount,
    InstagramMedia,
    PostInsights,
)


# ─── Default field selectors (Graph `fields=` query param) ────────────────

PAGE_FIELDS = (
    "id,name,category,access_token,fan_count,followers_count,link,tasks"
)

POST_FIELDS = (
    "id,message,created_time,permalink_url,full_picture,"
    "attachments{title,description,type,media_type,unshimmed_url},"
    "likes.summary(true).limit(0),"
    "comments.summary(true).limit(0),"
    "shares"
)

IG_ACCOUNT_FIELDS = (
    "id,username,name,profile_picture_url,"
    "followers_count,follows_count,media_count,biography,website"
)

IG_MEDIA_FIELDS = (
    "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp,"
    "like_count,comments_count"
)

ME_FIELDS = "id,name"

PAGE_IG_FIELD = "instagram_business_account"


# ─── Default insight metric lists ─────────────────────────────────────────

POST_INSIGHT_METRICS = [
    "post_impressions",
    "post_impressions_unique",  # == reach
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
    "video_views",  # only meaningful for VIDEO / REELS
]

# Account-level (IG User) insights — the `/{ig-user-id}/insights` endpoint,
# distinct from the per-media `/{media-id}/insights` above. Conservative
# default: the three long-stable `period=day` account metrics that need no
# `metric_type=total_value` handling and no extra scope beyond
# `instagram_manage_insights`. `impressions` was retired at the account level
# in Graph v22 (kept only per-media, and even there via `views` in newer
# versions) — deliberately EXCLUDED here so the default call never 400s on a
# current app. Richer metrics (`accounts_engaged`, `total_interactions`,
# `website_clicks`, `views`) are opt-in via the method's `metrics=` param once
# the live account confirms which its app version exposes (calibrate against
# the real token — mirrors the WAHA response-shape-drift discipline). The
# adapter keeps the raw daily series on `PostInsights.raw`, so no metric's
# per-day breakdown is lost even though `metrics` flattens to one number each.
IG_ACCOUNT_INSIGHT_METRICS = [
    "reach",
    "profile_views",
    "follower_count",
]


# ─── Datetime ─────────────────────────────────────────────────────────────


def parse_graph_datetime(value: str | None) -> datetime | None:
    """Parse Graph's timestamp formats into an aware ``datetime``.

    Graph emits `2026-05-13T18:30:00+0000` (no colon in the offset),
    which `datetime.fromisoformat` rejects pre-3.11 and still parses
    inconsistently across versions. We normalize the `+HHMM` /
    `-HHMM` tail to `+HH:MM` first, and tolerate a trailing `Z`.
    Returns `None` for falsy input."""

    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Normalize a `+0000` / `-0530` style offset (no colon) to `+00:00`.
    if len(text) >= 5:
        tail = text[-5:]
        if (tail[0] in "+-") and tail[1:].isdigit():
            text = text[:-5] + tail[0] + tail[1:3] + ":" + tail[3:]
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ─── Edge-summary helper ──────────────────────────────────────────────────


def _summary_count(edge: Any) -> int:
    """Extract `summary.total_count` from a `.summary(true).limit(0)`
    edge, or fall back to `len(data)`. Tolerant of missing keys."""

    if not isinstance(edge, dict):
        return 0
    summary = edge.get("summary")
    if isinstance(summary, dict) and summary.get("total_count") is not None:
        try:
            return int(summary["total_count"])
        except (TypeError, ValueError):
            return 0
    data = edge.get("data")
    if isinstance(data, list):
        return len(data)
    return 0


def _shares_count(value: Any) -> int:
    """`shares` comes back as `{"count": N}` (or absent)."""

    if isinstance(value, dict):
        try:
            return int(value.get("count", 0))
        except (TypeError, ValueError):
            return 0
    return 0


# ─── Body → dataclass mappers ─────────────────────────────────────────────


def page_from_body(body: dict[str, Any]) -> FacebookPage:
    return FacebookPage(
        id=str(body["id"]),
        name=body.get("name", ""),
        category=body.get("category"),
        access_token=body.get("access_token"),
        fan_count=body.get("fan_count"),
        followers_count=body.get("followers_count"),
        link=body.get("link"),
        tasks=list(body.get("tasks") or []),
    )


def post_from_body(body: dict[str, Any]) -> FacebookPost:
    return FacebookPost(
        id=str(body["id"]),
        message=body.get("message"),
        created_time=parse_graph_datetime(body.get("created_time")),
        permalink_url=body.get("permalink_url"),
        full_picture=body.get("full_picture"),
        likes=_summary_count(body.get("likes")),
        comments=_summary_count(body.get("comments")),
        shares=_shares_count(body.get("shares")),
        attachments=list(
            (body.get("attachments") or {}).get("data", [])
            if isinstance(body.get("attachments"), dict)
            else []
        ),
    )


def ig_account_from_body(
    body: dict[str, Any], *, page_id: str | None = None
) -> InstagramAccount:
    return InstagramAccount(
        id=str(body["id"]),
        username=body.get("username", ""),
        name=body.get("name"),
        profile_picture_url=body.get("profile_picture_url"),
        followers_count=body.get("followers_count"),
        follows_count=body.get("follows_count"),
        media_count=body.get("media_count"),
        biography=body.get("biography"),
        website=body.get("website"),
        page_id=page_id,
    )


def ig_media_from_body(body: dict[str, Any]) -> InstagramMedia:
    return InstagramMedia(
        id=str(body["id"]),
        caption=body.get("caption"),
        media_type=body.get("media_type"),
        media_url=body.get("media_url"),
        permalink=body.get("permalink"),
        thumbnail_url=body.get("thumbnail_url"),
        timestamp=parse_graph_datetime(body.get("timestamp")),
        like_count=int(body.get("like_count") or 0),
        comments_count=int(body.get("comments_count") or 0),
    )


def _metric_value(values: Any) -> int:
    """Flatten an insight metric's `values` list into a single int.

    `values` is `[{"value": <int|dict>}]`. Dict-valued payloads
    (`post_reactions_by_type_total`) get summed into a flat int."""

    if not isinstance(values, list) or not values:
        return 0
    raw = values[0].get("value") if isinstance(values[0], dict) else None
    if isinstance(raw, dict):
        total = 0
        for v in raw.values():
            try:
                total += int(v)
            except (TypeError, ValueError):
                continue
        return total
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def insights_from_body(
    object_id: str, body: dict[str, Any]
) -> PostInsights:
    """Map `/{id}/insights` `{"data": [{name, period, values}]}`."""

    rows = body.get("data") or []
    metrics: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not name:
            continue
        metrics[name] = _metric_value(row.get("values"))
    return PostInsights(object_id=object_id, metrics=metrics, raw=list(rows))


__all__ = [
    "IG_ACCOUNT_FIELDS",
    "IG_ACCOUNT_INSIGHT_METRICS",
    "IG_MEDIA_FIELDS",
    "IG_MEDIA_INSIGHT_METRICS",
    "ME_FIELDS",
    "PAGE_FIELDS",
    "PAGE_IG_FIELD",
    "POST_FIELDS",
    "POST_INSIGHT_METRICS",
    "ig_account_from_body",
    "ig_media_from_body",
    "insights_from_body",
    "page_from_body",
    "parse_graph_datetime",
    "post_from_body",
]
