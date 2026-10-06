"""Instagram API **with Instagram Login** — insights value objects, metric
catalogs and pure parsers (zero IO).

The read model behind ``InstagramLoginInsightsAdapter`` (see
``instagram_login_adapter``). Everything here is Meta-documented knowledge,
pinned with its source so a future metric retirement is a one-line diff:

- IG User fields — ``GET graph.instagram.com/<v>/me?fields=...``
  https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/get-started
- IG User insights — ``GET /<IG_ID>/insights`` (``metric_type`` =
  ``total_value`` | ``time_series``; ``period=day``)
  https://developers.facebook.com/docs/instagram-platform/api-reference/instagram-user/insights
- IG Media fields + edges
  https://developers.facebook.com/docs/instagram-platform/reference/instagram-media
- IG Media insights — ``GET /<IG_MEDIA_ID>/insights`` (metric availability
  per ``media_product_type``)
  https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/insights
- IG User media / stories edges (10K most-recent cap; stories NOT on
  ``/media``, use ``/stories``)
  https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/

Unknown / unsupported metrics are NEVER coerced to ``0``: a metric Meta did
not return (or rejected for this media type) is ``None`` in ``values`` AND
named in ``unsupported`` so the caller can log/persist the gap.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from noctusai_lib.integrations.meta.mappers import parse_graph_datetime

logger = logging.getLogger(__name__)

__all__ = [
    "IG_PROFILE_FIELDS",
    "IG_PROFILE_CORE_FIELDS",
    "IG_MEDIA_LIST_FIELDS",
    "IG_MEDIA_LIST_CORE_FIELDS",
    "IG_USER_TOTAL_VALUE_METRICS",
    "IG_USER_TIME_SERIES_METRICS",
    "IG_MEDIA_METRICS_BY_PRODUCT_TYPE",
    "IgProfile",
    "IgMediaItem",
    "IgMediaPage",
    "IgMetricsResult",
    "IgUserInsights",
    "effective_product_type",
    "media_metrics_for",
    "ig_profile_from_body",
    "ig_media_item_from_body",
    "metric_values_from_body",
    "metric_series_from_body",
]

# ─── Field sets ───────────────────────────────────────────────────────────
# `user_id` is the IG professional-account id (the node the insights edge
# hangs off); `id` on /me is the app-scoped id. `biography`/`website` are IG
# User node fields; if Graph rejects either for this token the adapter
# retries with the CORE set and logs the drop (never a silent empty profile).
IG_PROFILE_CORE_FIELDS: tuple[str, ...] = (
    "id",
    "user_id",
    "username",
    "name",
    "account_type",
    "profile_picture_url",
    "followers_count",
    "follows_count",
    "media_count",
)
IG_PROFILE_FIELDS: tuple[str, ...] = IG_PROFILE_CORE_FIELDS + ("biography", "website")

# Meta's IG Media reference annotates `caption` and `media_product_type` as
# "Available for Instagram API with Facebook Login only". In practice
# graph.instagram.com serves both for the account's own media, but we do NOT
# depend on it: the adapter asks for the FULL set and, on a field rejection
# (Graph code 100), retries with the CORE set and logs it. A missing
# `media_product_type` is then left `None` (persisted as such) and the metric
# set is chosen from `media_type` via `effective_product_type` (documented
# inference, never written back as if Meta had said it).
IG_MEDIA_LIST_CORE_FIELDS: tuple[str, ...] = (
    "id",
    "media_type",
    "media_url",
    "permalink",
    "thumbnail_url",
    "timestamp",
    "like_count",
    "comments_count",
)
IG_MEDIA_LIST_FIELDS: tuple[str, ...] = IG_MEDIA_LIST_CORE_FIELDS + (
    "caption",
    "media_product_type",
    "is_shared_to_feed",
)

# ─── IG User insights (account level) ─────────────────────────────────────
# Per the IG User insights reference (Instagram Login): every metric below is
# `period=day`; all support `metric_type=total_value`, only `reach` (and the
# retired `impressions`) support `time_series`. `impressions` is deprecated
# (v22.0+, retired 2025-04-21) and deliberately absent. `profile_views` /
# `website_clicks` / `follower_count` are NOT in the Instagram-Login metric
# table — follower growth is derived from the daily `followers_count` field.
IG_USER_TOTAL_VALUE_METRICS: tuple[str, ...] = (
    "reach",
    "views",
    "accounts_engaged",
    "total_interactions",
    "likes",
    "comments",
    "shares",
    "saves",
    "replies",
    "reposts",
    "profile_links_taps",
    "follows_and_unfollows",
)
IG_USER_TIME_SERIES_METRICS: tuple[str, ...] = ("reach",)

# ─── IG Media insights per media_product_type ─────────────────────────────
# Transcribed from the IG Media insights reference metric/media-type matrix.
# `impressions` (deprecated for media created after 2024-07-02) and the
# breakdown-only metrics are omitted. CAROUSEL_ALBUM parents publish as
# product type FEED and take the FEED set — "Insights data is not available
# for any media WITHIN an album" refers to the children, which we never
# query. Any metric Graph still rejects for a given object degrades to
# `None` + `unsupported` (per-metric retry in the adapter), never 0.
IG_MEDIA_METRICS_BY_PRODUCT_TYPE: dict[str, tuple[str, ...]] = {
    "FEED": (
        "views",
        "reach",
        "likes",
        "comments",
        "shares",
        "saved",
        "total_interactions",
        "follows",
        "profile_visits",
        "profile_activity",
        "reposts",
        "facebook_views",
    ),
    "REELS": (
        "views",
        "reach",
        "likes",
        "comments",
        "shares",
        "saved",
        "total_interactions",
        "ig_reels_avg_watch_time",
        "ig_reels_video_view_total_time",
        "reels_skip_rate",
        "reposts",
        "crossposted_views",
        "facebook_views",
    ),
    "STORY": (
        "views",
        "reach",
        "shares",
        "total_interactions",
        "follows",
        "profile_visits",
        "profile_activity",
        "replies",
        "navigation",
        "reposts",
        "facebook_views",
    ),
}


def effective_product_type(
    media_product_type: str | None, media_type: str | None
) -> str:
    """The product type used to CHOOSE the metric set.

    Meta's value wins when present. When Graph did not return it (see the
    field-set note above), infer from ``media_type``: every feed video
    published since 2022 is a Reel, so ``VIDEO`` → ``REELS``; anything else →
    ``FEED``. ``AD`` (boosted) maps to ``FEED`` (same metric surface). The
    inference is used only for metric selection — callers persist Meta's raw
    ``media_product_type`` (possibly ``None``)."""
    mpt = (media_product_type or "").upper()
    if mpt in IG_MEDIA_METRICS_BY_PRODUCT_TYPE:
        return mpt
    if mpt == "AD":
        return "FEED"
    if (media_type or "").upper() == "VIDEO":
        return "REELS"
    return "FEED"


def media_metrics_for(media_product_type: str | None, media_type: str | None) -> tuple[str, ...]:
    return IG_MEDIA_METRICS_BY_PRODUCT_TYPE[
        effective_product_type(media_product_type, media_type)
    ]


# ─── Value objects ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class IgProfile:
    """The connected IG professional account (``/me``)."""

    id: str
    user_id: str | None
    username: str
    name: str | None = None
    account_type: str | None = None
    profile_picture_url: str | None = None
    followers_count: int | None = None
    follows_count: int | None = None
    media_count: int | None = None
    biography: str | None = None
    website: str | None = None

    @property
    def ig_user_id(self) -> str:
        """The professional-account id insights hang off (falls back to the
        app-scoped ``id`` when Graph omitted ``user_id``)."""
        return self.user_id or self.id


@dataclass(frozen=True)
class IgMediaItem:
    """One IG media object as listed by ``/me/media`` or ``/me/stories``.

    ``like_count`` is ``None`` when the owner hid like counts (Graph omits
    the field) — never defaulted to 0."""

    id: str
    media_type: str | None = None
    media_product_type: str | None = None
    caption: str | None = None
    permalink: str | None = None
    thumbnail_url: str | None = None
    media_url: str | None = None
    timestamp: datetime | None = None
    like_count: int | None = None
    comments_count: int | None = None
    is_shared_to_feed: bool | None = None


@dataclass(frozen=True)
class IgMediaPage:
    items: list[IgMediaItem]
    next_cursor: str | None = None


@dataclass(frozen=True)
class IgMetricsResult:
    """Per-object metric values. ``values`` holds EVERY requested metric —
    ``None`` for the ones Meta did not serve, which are also listed in
    ``unsupported`` (reason in ``errors[metric]`` when Graph gave one)."""

    object_id: str
    values: dict[str, float | int | None]
    unsupported: tuple[str, ...] = ()
    errors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IgUserInsights:
    """Account-level insights for a ``since``/``until`` window.

    ``totals`` — ``metric_type=total_value`` (one number per metric for the
    window); ``series`` — ``metric_type=time_series`` per-day points
    ``[(YYYY-MM-DD, value)]``. Unsupported metrics are ``None`` in ``totals``
    and named in ``unsupported``."""

    totals: dict[str, float | int | None]
    series: dict[str, list[tuple[str, float | int | None]]] = field(default_factory=dict)
    unsupported: tuple[str, ...] = ()
    errors: dict[str, str] = field(default_factory=dict)


# ─── Pure parsers ─────────────────────────────────────────────────────────
def _opt_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def ig_profile_from_body(body: dict[str, Any]) -> IgProfile:
    return IgProfile(
        id=str(body.get("id") or body.get("user_id") or ""),
        user_id=str(body["user_id"]) if body.get("user_id") is not None else None,
        username=str(body.get("username") or ""),
        name=body.get("name"),
        account_type=body.get("account_type"),
        profile_picture_url=body.get("profile_picture_url"),
        followers_count=_opt_int(body.get("followers_count")),
        follows_count=_opt_int(body.get("follows_count")),
        media_count=_opt_int(body.get("media_count")),
        biography=body.get("biography"),
        website=body.get("website"),
    )


def ig_media_item_from_body(
    body: dict[str, Any], *, default_product_type: str | None = None
) -> IgMediaItem:
    """``default_product_type`` is set by the ``/stories`` lister (every item
    on that edge IS a story, whether or not Graph echoed the field)."""
    shared = body.get("is_shared_to_feed")
    return IgMediaItem(
        id=str(body["id"]),
        media_type=body.get("media_type"),
        media_product_type=body.get("media_product_type") or default_product_type,
        caption=body.get("caption"),
        permalink=body.get("permalink"),
        thumbnail_url=body.get("thumbnail_url"),
        media_url=body.get("media_url"),
        timestamp=parse_graph_datetime(body.get("timestamp")),
        like_count=_opt_int(body.get("like_count")),
        comments_count=_opt_int(body.get("comments_count")),
        is_shared_to_feed=shared if isinstance(shared, bool) else None,
    )


def _number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, dict):
        # A breakdown-shaped value ({"a": 1, "b": 2}) — sum it to the total.
        nums = [v for v in value.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        return sum(nums) if nums else None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else f


def metric_values_from_body(body: dict[str, Any]) -> dict[str, float | int | None]:
    """``{"data": [{name, values:[{value}]} | {name, total_value:{value}}]}``
    → ``{name: number|None}``. Only metrics PRESENT in the body appear."""
    out: dict[str, float | int | None] = {}
    for row in body.get("data") or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        name = str(row["name"])
        if isinstance(row.get("total_value"), dict):
            out[name] = _number(row["total_value"].get("value"))
            continue
        values = row.get("values") or []
        if values and isinstance(values[-1], dict):
            out[name] = _number(values[-1].get("value"))
        else:
            out[name] = None
    return out


def metric_series_from_body(
    body: dict[str, Any],
) -> dict[str, list[tuple[str, float | int | None]]]:
    """``time_series`` rows → ``{name: [(YYYY-MM-DD, value)]}`` keyed on each
    point's ``end_time`` date (Graph's day bucket end)."""
    out: dict[str, list[tuple[str, float | int | None]]] = {}
    for row in body.get("data") or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        points: list[tuple[str, float | int | None]] = []
        for v in row.get("values") or []:
            if not isinstance(v, dict):
                continue
            end = parse_graph_datetime(v.get("end_time"))
            if end is None:
                continue
            points.append((end.date().isoformat(), _number(v.get("value"))))
        out[str(row["name"])] = points
    return out
