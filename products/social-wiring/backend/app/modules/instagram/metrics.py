"""Presentation catalog for Instagram metrics — pt-BR labels, value format
and "most relevant first" priority per media product type.

WHICH metrics exist per media type is Meta knowledge and lives in the seed
(``noctusai_lib.integrations.meta.instagram_insights.
IG_MEDIA_METRICS_BY_PRODUCT_TYPE``); this module only says how the product
SHOWS them. A test pins that every seed metric has a label here, so a metric
Meta adds to the seed catalog can't render unlabeled.

Priority rationale (1 = shown first):
- REELS — distribution (views, reach), then retention (avg watch time) —
  the signal the Reels algorithm weighs most — then engagement.
- FEED / CAROUSEL — distribution, then total + per-type engagement, then
  profile conversion (profile visits, follows).
- STORY — distribution, then the story-native responses (replies,
  navigation), then engagement and profile conversion.
Cross-posting counters (Facebook views, reposts) always trail.
"""
from __future__ import annotations

from typing import Literal

from noctusai_lib.integrations.meta import (
    IG_MEDIA_METRICS_BY_PRODUCT_TYPE,
    effective_product_type,
)

Format = Literal["int", "duration_ms", "percent"]

# key → (pt-BR label, format)
METRIC_META: dict[str, tuple[str, Format]] = {
    "views": ("Visualizações", "int"),
    "reach": ("Contas alcançadas", "int"),
    "likes": ("Curtidas", "int"),
    "comments": ("Comentários", "int"),
    "shares": ("Compartilhamentos", "int"),
    "saved": ("Salvamentos", "int"),
    "total_interactions": ("Interações", "int"),
    "follows": ("Novos seguidores", "int"),
    "profile_visits": ("Visitas ao perfil", "int"),
    "profile_activity": ("Ações no perfil", "int"),
    "reposts": ("Republicações", "int"),
    "facebook_views": ("Visualizações no Facebook", "int"),
    "crossposted_views": ("Visualizações (cross-post)", "int"),
    # Meta documents the unit as unspecified; Graph returns milliseconds.
    "ig_reels_avg_watch_time": ("Tempo médio assistido", "duration_ms"),
    "ig_reels_video_view_total_time": ("Tempo total assistido", "duration_ms"),
    "reels_skip_rate": ("Taxa de pulo (3s)", "percent"),
    "replies": ("Respostas", "int"),
    "navigation": ("Navegação", "int"),
}

MEDIA_PRIORITY: dict[str, tuple[str, ...]] = {
    "REELS": (
        "views",
        "reach",
        "ig_reels_avg_watch_time",
        "total_interactions",
        "likes",
        "comments",
        "shares",
        "saved",
        "reels_skip_rate",
        "ig_reels_video_view_total_time",
        "reposts",
        "facebook_views",
        "crossposted_views",
    ),
    "FEED": (
        "views",
        "reach",
        "total_interactions",
        "likes",
        "comments",
        "shares",
        "saved",
        "profile_visits",
        "follows",
        "profile_activity",
        "reposts",
        "facebook_views",
    ),
    "STORY": (
        "views",
        "reach",
        "replies",
        "navigation",
        "total_interactions",
        "shares",
        "profile_visits",
        "follows",
        "profile_activity",
        "reposts",
        "facebook_views",
    ),
}

# Account-level (profile trend). `followers_count`/`follows_count`/`media_count`
# come from the daily /me read; the rest are IG User insights (total_value for
# the previous BRT day).
PROFILE_METRIC_META: dict[str, tuple[str, Format]] = {
    "followers_count": ("Seguidores", "int"),
    "reach": ("Contas alcançadas", "int"),
    "views": ("Visualizações", "int"),
    "accounts_engaged": ("Contas com engajamento", "int"),
    "total_interactions": ("Interações", "int"),
    "likes": ("Curtidas", "int"),
    "comments": ("Comentários", "int"),
    "shares": ("Compartilhamentos", "int"),
    "saves": ("Salvamentos", "int"),
    "replies": ("Respostas", "int"),
    "reposts": ("Republicações", "int"),
    "profile_links_taps": ("Toques em links do perfil", "int"),
    "follows_and_unfollows": ("Seguiram / deixaram de seguir", "int"),
    "follows_count": ("Seguindo", "int"),
    "media_count": ("Publicações", "int"),
}


def media_metric_descriptors(
    media_product_type: str | None, media_type: str | None
) -> list[dict]:
    """``[{key, label, format, priority}]`` for this media, most relevant
    first — exactly the metrics the seed catalog requests for its type."""
    ptype = effective_product_type(media_product_type, media_type)
    order = MEDIA_PRIORITY[ptype]
    available = set(IG_MEDIA_METRICS_BY_PRODUCT_TYPE[ptype])
    out = []
    for i, key in enumerate(k for k in order if k in available):
        label, fmt = METRIC_META[key]
        out.append({"key": key, "label": label, "format": fmt, "priority": i + 1})
    return out


def profile_metric_descriptors() -> list[dict]:
    return [
        {"key": k, "label": label, "format": fmt, "priority": i + 1}
        for i, (k, (label, fmt)) in enumerate(PROFILE_METRIC_META.items())
    ]


__all__ = [
    "METRIC_META",
    "MEDIA_PRIORITY",
    "PROFILE_METRIC_META",
    "media_metric_descriptors",
    "profile_metric_descriptors",
]
