"""meta.instagram.* tools — Graph read-only Instagram surface.

Tools registered:
- meta.instagram.list_accounts — IG Business accounts linked to Pages.
- meta.instagram.list_media    — media items for an IG account.
- meta.instagram.media_insights — flattened per-media insight metrics.

All PURE reads — no side-effect, no confirm gate (READ-ONLY v1; the
backing seed `MetaAdapter` Protocol has no IG-publish methods — Meta
App Review gates the content-publishing scopes).

Thin wrappers over `noctusai_lib.integrations.meta` (verified to ship
`get_meta_adapter` / `FakeMetaAdapter` / `InstagramAccount` /
`InstagramMedia` / `PostInsights` / `MetaGraphError` —
verify-the-seed-ships-it). Nothing is re-implemented here.

Deferred-config rule + the `_meta_error` enrichment mirror
`tools/facebook.py` exactly (same seed package, same error contract).
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.meta import (
    MetaGraphError,
    get_meta_adapter,
)

from ..settings import get_settings
from ..types import (
    InstagramAccountOut,
    InstagramMediaOut,
    ListAccountsInput,
    ListAccountsOutput,
    ListMediaInput,
    ListMediaOutput,
    MediaInsightsInput,
    MediaInsightsOutput,
    PostInsightsOut,
    PublishedMediaOut,
    PublishMediaInput,
    PublishMediaOutput,
)

logger = logging.getLogger(__name__)


def _adapter():
    s = get_settings()
    return get_meta_adapter(
        system_user_token=s.meta_system_user_token,
        graph_version=None,
    )


def _meta_error(e: MetaGraphError) -> dict:
    """Typed-error envelope enriched with Meta's branchable signals.

    Identical contract to `tools/facebook._meta_error` — Graph errors
    carry `.http_status` + `is_auth_error` / `is_rate_limited`, which
    `_kit.errors.typed_error` (probing `.status`) does not surface.
    """
    env = typed_error(e)
    env["http_status"] = e.http_status
    env["is_auth_error"] = e.is_auth_error
    env["is_rate_limited"] = e.is_rate_limited
    env["requires_app_review"] = getattr(e, "requires_app_review", False)
    return env


def _account_out(a) -> InstagramAccountOut:
    return InstagramAccountOut(
        id=a.id,
        username=a.username,
        name=a.name,
        profile_picture_url=a.profile_picture_url,
        followers_count=a.followers_count,
        follows_count=a.follows_count,
        media_count=a.media_count,
        biography=a.biography,
        website=a.website,
        page_id=a.page_id,
    )


def _media_out(m) -> InstagramMediaOut:
    return InstagramMediaOut(
        id=m.id,
        caption=m.caption,
        media_type=m.media_type,
        media_url=m.media_url,
        permalink=m.permalink,
        thumbnail_url=m.thumbnail_url,
        timestamp=m.timestamp.isoformat() if m.timestamp else None,
        like_count=m.like_count,
        comments_count=m.comments_count,
    )


# ─── Handlers ────────────────────────────────────────────────────────────


async def list_accounts(args: dict) -> dict:
    ListAccountsInput(**args)
    adapter = _adapter()
    try:
        accounts = adapter.list_instagram_accounts()
    except MetaGraphError as e:
        return ListAccountsOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return ListAccountsOutput(
        accounts=[_account_out(a) for a in accounts],
        auth_mode=adapter.auth_mode,
    ).model_dump()


async def list_media(args: dict) -> dict:
    inp = ListMediaInput(**args)
    adapter = _adapter()
    try:
        media = adapter.list_instagram_media(inp.ig_user_id, limit=inp.limit)
    except MetaGraphError as e:
        return ListMediaOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return ListMediaOutput(
        media=[_media_out(m) for m in media],
        auth_mode=adapter.auth_mode,
    ).model_dump()


async def media_insights(args: dict) -> dict:
    inp = MediaInsightsInput(**args)
    adapter = _adapter()
    try:
        ins = adapter.get_instagram_media_insights(inp.media_id)
    except MetaGraphError as e:
        return MediaInsightsOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return MediaInsightsOutput(
        insights=PostInsightsOut(
            object_id=ins.object_id,
            metrics=dict(ins.metrics),
            raw=list(ins.raw),
        ),
        auth_mode=adapter.auth_mode,
    ).model_dump()


async def publish_media(args: dict) -> dict:
    inp = PublishMediaInput(**args)
    if not inp.confirm:
        return PublishMediaOutput(
            error=typed_error(
                PermissionError(
                    "meta.instagram.publish_media is a WRITE — re-call with "
                    "confirm=true to publish."
                )
            )
        ).model_dump()
    adapter = _adapter()
    logger.info(
        "meta.instagram.publish_media AUDIT confirmed=true ig_user_id=%s",
        inp.ig_user_id,
    )
    try:
        pub = adapter.publish_instagram_media(
            inp.ig_user_id, inp.image_url, caption=inp.caption
        )
    except MetaGraphError as e:
        return PublishMediaOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return PublishMediaOutput(
        published=PublishedMediaOut(
            id=pub.id,
            ig_user_id=pub.ig_user_id,
            container_id=pub.container_id,
            caption=pub.caption,
            permalink=pub.permalink,
        ),
        auth_mode=adapter.auth_mode,
    ).model_dump()


# ─── Registration ───────────────────────────────────────────────────────


HANDLERS = {
    "meta.instagram.list_accounts": list_accounts,
    "meta.instagram.list_media": list_media,
    "meta.instagram.media_insights": media_insights,
    "meta.instagram.publish_media": publish_media,
}


def register(server: Server) -> dict:
    """Return this module's {tool_name: handler} map.

    The server aggregates these via `_kit.registry.build_registry`.
    """
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="meta.instagram.list_accounts",
            description=(
                "List the Instagram Business/Creator accounts linked to "
                "the managed Facebook Pages. READ-ONLY — no side-effect, "
                "no confirm. `auth_mode` tells you which backend answered."
            ),
            inputSchema=ListAccountsInput.model_json_schema(),
        ),
        Tool(
            name="meta.instagram.list_media",
            description=(
                "List media items (image/video/carousel) for an Instagram "
                "Business account. READ-ONLY. `ig_user_id` required; "
                "`limit` caps the page (1-100). Stories excluded."
            ),
            inputSchema=ListMediaInput.model_json_schema(),
        ),
        Tool(
            name="meta.instagram.media_insights",
            description=(
                "Fetch flattened insight metrics for a single Instagram "
                "media item. READ-ONLY. `media_id` required. Returns a "
                "{metric: int} map plus the raw period-detail payload."
            ),
            inputSchema=MediaInsightsInput.model_json_schema(),
        ),
        Tool(
            name="meta.instagram.publish_media",
            description=(
                "Publish an image to an Instagram Business account "
                "(container→publish). WRITE — you MUST pass confirm=true or "
                "it is refused with a typed error and nothing is published. "
                "Real path needs App-Review-approved content-publishing "
                "scope; absent → typed error requires_app_review=true "
                "(never faked). Fake simulates+records when unconfigured."
            ),
            inputSchema=PublishMediaInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
