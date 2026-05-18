"""meta.facebook.* tools — Graph read-only Page surface.

Tools registered:
- meta.facebook.list_pages      — Pages the identity manages.
- meta.facebook.list_page_posts — posts authored by a Page.
- meta.facebook.post_insights   — flattened per-post insight metrics.

All PURE reads — no side-effect, no confirm gate (READ-ONLY v1; the
backing seed `MetaAdapter` Protocol intentionally has no write methods —
Meta App Review gates the write scopes).

Thin wrappers over `noctusai_lib.integrations.meta` (verified to ship
`get_meta_adapter` / `FakeMetaAdapter` / `FacebookPage` / `FacebookPost`
/ `PostInsights` / `MetaGraphError` — verify-the-seed-ships-it; read
its `__init__.py` `__all__`). Nothing is re-implemented here.

Deferred-config rule: with no `META_SYSTEM_USER_TOKEN` (and no resolver),
`get_meta_adapter` returns `FakeMetaAdapter`, so the server boots and
these tools answer deterministically; with a System User Token it
returns the live `MetaOAuthAdapter`.

`MetaGraphError` carries `http_status` (not `status`) — the shared
`_kit.errors.typed_error` probes `getattr(e, "status", None)`, so the
envelope's `status` is None for Graph errors. `_meta_error(...)`
enriches the typed-error dict with `is_auth_error` / `is_rate_limited`
/ `http_status` so the host LLM can still branch deterministically.
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
    FacebookPageOut,
    FacebookPostOut,
    ListPagePostsInput,
    ListPagePostsOutput,
    ListPagesInput,
    ListPagesOutput,
    PostInsightsInput,
    PostInsightsOut,
    PostInsightsOutput,
    PublishedPostOut,
    PublishPostInput,
    PublishPostOutput,
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

    `_kit.errors.typed_error` only probes `.status`; Graph errors carry
    `.http_status` + `is_auth_error` / `is_rate_limited`. Surface all
    three so the host LLM branches deterministically (re-consent vs
    back-off vs hard failure).
    """
    env = typed_error(e)
    env["http_status"] = e.http_status
    env["is_auth_error"] = e.is_auth_error
    env["is_rate_limited"] = e.is_rate_limited
    env["requires_app_review"] = getattr(e, "requires_app_review", False)
    return env


def _page_out(p) -> FacebookPageOut:
    # access_token deliberately omitted — never leak a credential.
    return FacebookPageOut(
        id=p.id,
        name=p.name,
        category=p.category,
        fan_count=p.fan_count,
        followers_count=p.followers_count,
        link=p.link,
        tasks=list(p.tasks),
    )


def _post_out(p) -> FacebookPostOut:
    return FacebookPostOut(
        id=p.id,
        message=p.message,
        created_time=p.created_time.isoformat() if p.created_time else None,
        permalink_url=p.permalink_url,
        full_picture=p.full_picture,
        likes=p.likes,
        comments=p.comments,
        shares=p.shares,
        attachments=list(p.attachments),
    )


# ─── Handlers ────────────────────────────────────────────────────────────


async def list_pages(args: dict) -> dict:
    ListPagesInput(**args)
    adapter = _adapter()
    try:
        pages = adapter.list_facebook_pages()
    except MetaGraphError as e:
        return ListPagesOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return ListPagesOutput(
        pages=[_page_out(p) for p in pages],
        auth_mode=adapter.auth_mode,
    ).model_dump()


async def list_page_posts(args: dict) -> dict:
    inp = ListPagePostsInput(**args)
    adapter = _adapter()
    try:
        posts = adapter.list_facebook_posts(inp.page_id, limit=inp.limit)
    except MetaGraphError as e:
        return ListPagePostsOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return ListPagePostsOutput(
        posts=[_post_out(p) for p in posts],
        auth_mode=adapter.auth_mode,
    ).model_dump()


async def post_insights(args: dict) -> dict:
    inp = PostInsightsInput(**args)
    adapter = _adapter()
    try:
        ins = adapter.get_facebook_post_insights(
            inp.post_id, page_id=inp.page_id
        )
    except MetaGraphError as e:
        return PostInsightsOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return PostInsightsOutput(
        insights=PostInsightsOut(
            object_id=ins.object_id,
            metrics=dict(ins.metrics),
            raw=list(ins.raw),
        ),
        auth_mode=adapter.auth_mode,
    ).model_dump()


async def publish_post(args: dict) -> dict:
    inp = PublishPostInput(**args)
    if not inp.confirm:
        return PublishPostOutput(
            error=typed_error(
                PermissionError(
                    "meta.facebook.publish_post is a WRITE — re-call with "
                    "confirm=true to publish."
                )
            )
        ).model_dump()
    adapter = _adapter()
    logger.info(
        "meta.facebook.publish_post AUDIT confirmed=true page_id=%s", inp.page_id
    )
    try:
        pub = adapter.publish_facebook_post(
            inp.page_id, inp.message, link=inp.link, photo_url=inp.photo_url
        )
    except MetaGraphError as e:
        return PublishPostOutput(
            auth_mode=adapter.auth_mode, error=_meta_error(e)
        ).model_dump()
    return PublishPostOutput(
        published=PublishedPostOut(
            id=pub.id,
            page_id=pub.page_id,
            message=pub.message,
            permalink_url=pub.permalink_url,
        ),
        auth_mode=adapter.auth_mode,
    ).model_dump()


# ─── Registration ───────────────────────────────────────────────────────


HANDLERS = {
    "meta.facebook.list_pages": list_pages,
    "meta.facebook.list_page_posts": list_page_posts,
    "meta.facebook.post_insights": post_insights,
    "meta.facebook.publish_post": publish_post,
}


def register(server: Server) -> dict:
    """Return this module's {tool_name: handler} map.

    The server aggregates these via `_kit.registry.build_registry`.
    """
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="meta.facebook.list_pages",
            description=(
                "List the Facebook Pages the authenticated Meta identity "
                "manages. READ-ONLY — no side-effect, no confirm. Returns "
                "page metadata (no access tokens). `auth_mode` tells you "
                "which backend answered (system_user / user_oauth / none)."
            ),
            inputSchema=ListPagesInput.model_json_schema(),
        ),
        Tool(
            name="meta.facebook.list_page_posts",
            description=(
                "List posts authored by a Facebook Page. READ-ONLY. "
                "`page_id` required; `limit` caps the page (1-100). "
                "Like/comment/share are counts only — no liker lists."
            ),
            inputSchema=ListPagePostsInput.model_json_schema(),
        ),
        Tool(
            name="meta.facebook.post_insights",
            description=(
                "Fetch flattened insight metrics for a single Facebook "
                "post. READ-ONLY. `post_id` required; `page_id` optional "
                "(aids token selection). Returns a {metric: int} map plus "
                "the raw period-detail payload."
            ),
            inputSchema=PostInsightsInput.model_json_schema(),
        ),
        Tool(
            name="meta.facebook.publish_post",
            description=(
                "Publish a post to a Facebook Page. WRITE — you MUST pass "
                "confirm=true or it is refused with a typed error and "
                "nothing is posted. Real path needs App-Review-approved "
                "publishing scope; absent → typed error with "
                "requires_app_review=true (never a faked success). Fake "
                "adapter simulates+records when unconfigured."
            ),
            inputSchema=PublishPostInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
