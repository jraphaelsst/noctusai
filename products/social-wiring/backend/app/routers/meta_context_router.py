"""``GET /api/meta/context`` — one call resolving what a per-client Meta
connection can see (Wave 3).

Composes ``adapter.me()`` + ``list_facebook_pages()`` +
``list_instagram_accounts()`` over the SAME account-scoped adapter every
other Wave 3 router resolves via ``Depends(get_account_adapter)`` — the
FE's single round-trip to decide what to render (an Instagram tab, a
Facebook tab, both, or a "connect Meta" empty state).

``instagram`` is singular (``IGAccount | null``), not a list — mirrors
:func:`app.routers._meta_common.resolve_primary_ig_user_id`'s "exactly
one linked IG account in practice" assumption every other Wave 3 IG
endpoint relies on.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.routers._meta_common import (
    adapter_label as _adapter_label,
    get_account_adapter,
    handle_meta_graph_error,
)
from app.routers.meta_insights_router import IGAccountOut, ig_account_to_out
from app.services.meta import MetaAdapter, MetaGraphError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta-context"])


class FacebookPageOut(BaseModel):
    id: str
    name: str
    category: str | None = None
    fan_count: int | None = None
    followers_count: int | None = None
    link: str | None = None


class MetaUserOut(BaseModel):
    id: str | None = None
    name: str | None = None


class MetaContextResponse(BaseModel):
    instagram: IGAccountOut | None = None
    pages: list[FacebookPageOut] = []
    user: MetaUserOut | None = None
    adapter: str


def _page_out(page: Any) -> FacebookPageOut:
    return FacebookPageOut(
        id=page.id,
        name=page.name,
        category=page.category,
        fan_count=page.fan_count,
        followers_count=page.followers_count,
        link=page.link,
    )


@router.get("/api/meta/context", response_model=MetaContextResponse)
def get_meta_context(
    adapter: MetaAdapter = Depends(get_account_adapter),
) -> Any:
    """What this Meta connection sees: the linked Instagram Business/
    Creator account (if any), every managed Facebook Page, and the
    authenticated identity's ``id``/``name``.

    A ``MetaGraphError`` (bad/expired token, revoked scope) goes through
    the uniform Wave 3 gate — 200 structured on
    ``requires_app_review``, 502 structured otherwise — never a silent
    empty response."""
    try:
        me = adapter.me()
        pages = adapter.list_facebook_pages()
        ig_accounts = adapter.list_instagram_accounts()
    except MetaGraphError as exc:
        logger.warning("meta context: probe failed: %s", exc)
        return handle_meta_graph_error(exc)

    return MetaContextResponse(
        instagram=ig_account_to_out(ig_accounts[0]) if ig_accounts else None,
        pages=[_page_out(p) for p in pages],
        user=MetaUserOut(id=me.get("id"), name=me.get("name")) if me else None,
        adapter=_adapter_label(adapter),
    )


__all__ = ["router"]
