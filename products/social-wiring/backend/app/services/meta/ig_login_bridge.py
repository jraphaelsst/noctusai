"""Serve the legacy ``/api/meta/instagram/*`` insights endpoints from an
Instagram-Login (``provider="instagram"``) connection.

``meta_insights_router`` was written against the Facebook-Login
``MetaAdapter`` (IG account reached through a Page). This bridge implements
ONLY the four IG-insights methods those endpoints (and
``capture_ig_snapshot``) call, mapped onto the seed Instagram-Login adapter.
Everything else on ``MetaAdapter`` (Pages, publishing, comments, ads, leads)
is NOT bridged and raises ``NotImplementedError`` loudly — those surfaces
still require a Facebook-Login connection.

Legacy-shape caveat: ``PostInsights.metrics`` is ``dict[str, int]`` and cannot
carry ``None``; a metric Meta did not serve is therefore OMITTED from
``metrics`` (never written as 0) and logged; ``raw`` carries
``{"unsupported": [...]}`` so the gap stays visible.
"""
from __future__ import annotations

import logging
from typing import Any

from noctusai_lib.integrations.meta import (
    InstagramAccount,
    InstagramMedia,
    PostInsights,
)

logger = logging.getLogger(__name__)

__all__ = ["InstagramLoginInsightsBridge", "NotBridgedError"]


class NotBridgedError(NotImplementedError, AttributeError):
    """A ``MetaAdapter`` method with no Instagram-Login equivalent here.
    Also an ``AttributeError`` so ``hasattr`` probes answer False."""


def _int_metrics(values: dict[str, Any]) -> dict[str, int]:
    return {
        k: int(round(v))
        for k, v in values.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }


class InstagramLoginInsightsBridge:
    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        # media id → (media_product_type, media_type), learned from listings
        # so per-media insights request the right metric set.
        self._media_kind: dict[str, tuple[str | None, str | None]] = {}

    @property
    def ig_login_adapter(self) -> Any:
        return self._adapter

    def list_instagram_accounts(self) -> list[InstagramAccount]:
        p = self._adapter.get_profile()
        return [
            InstagramAccount(
                id=p.ig_user_id,
                username=p.username,
                name=p.name,
                profile_picture_url=p.profile_picture_url,
                followers_count=p.followers_count,
                follows_count=p.follows_count,
                media_count=p.media_count,
                biography=p.biography,
                website=p.website,
                page_id=None,  # no Facebook Page on this model
            )
        ]

    def list_instagram_media(self, ig_user_id: str, limit: int = 25) -> list[InstagramMedia]:
        out: list[InstagramMedia] = []
        cursor = None
        while len(out) < limit:
            page = self._adapter.list_media(cursor=cursor, limit=min(limit - len(out), 100))
            for m in page.items:
                self._media_kind[m.id] = (m.media_product_type, m.media_type)
                out.append(
                    InstagramMedia(
                        id=m.id,
                        caption=m.caption,
                        media_type=m.media_type,
                        media_url=m.media_url,
                        permalink=m.permalink,
                        thumbnail_url=m.thumbnail_url,
                        timestamp=m.timestamp,
                        # Legacy shape is non-optional int; hidden like counts
                        # (None) are surfaced as 0 by THIS legacy DTO only —
                        # the new /api/instagram surface keeps them null.
                        like_count=m.like_count or 0,
                        comments_count=m.comments_count or 0,
                    )
                )
            cursor = page.next_cursor
            if not cursor:
                break
        return out[:limit]

    def get_instagram_media_insights(self, media_id: str) -> PostInsights:
        mpt, mt = self._media_kind.get(media_id, (None, None))
        res = self._adapter.get_media_insights(media_id, mpt, media_type=mt)
        if res.unsupported:
            logger.info(
                "ig-login bridge: media %s metrics not served (omitted): %s",
                media_id, list(res.unsupported),
            )
        return PostInsights(
            object_id=media_id,
            metrics=_int_metrics(res.values),
            raw=[{"unsupported": list(res.unsupported)}],
        )

    def get_instagram_account_insights(
        self,
        ig_user_id: str,
        *,
        metrics: list[str] | None = None,
        period: str = "day",
        since: int | None = None,
        until: int | None = None,
    ) -> PostInsights:
        res = self._adapter.get_user_insights(
            ig_user_id,
            metrics,
            metric_type="total_value",
            period=period,
            since=since,
            until=until,
        )
        if res.unsupported:
            logger.info(
                "ig-login bridge: account %s metrics not served (omitted): %s",
                ig_user_id, list(res.unsupported),
            )
        return PostInsights(
            object_id=ig_user_id,
            metrics=_int_metrics(res.totals),
            raw=[{"unsupported": list(res.unsupported)}],
        )

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        raise NotBridgedError(
            f"{name} is not available on an Instagram-Login (provider='instagram') "
            "connection — this surface requires a Facebook-Login (provider='meta') account"
        )
