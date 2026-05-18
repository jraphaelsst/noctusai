"""Tests for the Meta connector MCP Graph leaves — facebook /
instagram / diagnostics.

No network. Two complementary surfaces are exercised:

1. The handler deferred-config path: with no `META_SYSTEM_USER_TOKEN`
   the seed factory `get_meta_adapter` returns `FakeMetaAdapter`, so
   the handlers answer deterministically (empty, `auth_mode="none"`)
   and the typed-error / output shapes are pinned.

2. The handler-internal mappers (`_page_out` / `_post_out` /
   `_account_out` / `_media_out`) driven by a *seeded*
   `FakeMetaAdapter` + real seed value objects — real code, zero
   monkeypatch (the seed Fake is the seed's own test double; nothing
   in our modules is replaced).

The `sys.path` bootstrap is shared with `test_smoke.py` (it imports
first, prepending this worktree's seed + `mcp/`).
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

# Reuse the shared sys.path bootstrap (prepends this worktree's seed
# + `mcp/` so `noctusai_lib.integrations.meta` resolves against the
# tree under test, not a stale editable-install worktree).
from . import test_smoke  # noqa: F401


# ─── Handler deferred-config path (empty FakeMetaAdapter) ────────────────


def test_facebook_list_pages_empty_fake_path():
    from meta.tools.facebook import list_pages

    out = asyncio.run(list_pages({}))
    assert out["pages"] == []
    assert out["auth_mode"] == "none"
    assert out["error"] is None


def test_facebook_list_page_posts_requires_page_id():
    from meta.tools.facebook import list_page_posts

    with pytest.raises(Exception):
        asyncio.run(list_page_posts({}))  # page_id is required


def test_facebook_list_page_posts_empty_fake_path():
    from meta.tools.facebook import list_page_posts

    out = asyncio.run(list_page_posts({"page_id": "P1", "limit": 10}))
    assert out["posts"] == []
    assert out["auth_mode"] == "none"
    assert out["error"] is None


def test_facebook_post_insights_empty_fake_path():
    from meta.tools.facebook import post_insights

    out = asyncio.run(post_insights({"post_id": "POST_1"}))
    assert out["insights"]["object_id"] == "POST_1"
    assert out["insights"]["metrics"] == {}
    assert out["auth_mode"] == "none"
    assert out["error"] is None


def test_instagram_list_accounts_empty_fake_path():
    from meta.tools.instagram import list_accounts

    out = asyncio.run(list_accounts({}))
    assert out["accounts"] == []
    assert out["auth_mode"] == "none"
    assert out["error"] is None


def test_instagram_list_media_empty_fake_path():
    from meta.tools.instagram import list_media

    out = asyncio.run(list_media({"ig_user_id": "IG1"}))
    assert out["media"] == []
    assert out["auth_mode"] == "none"
    assert out["error"] is None


def test_instagram_media_insights_empty_fake_path():
    from meta.tools.instagram import media_insights

    out = asyncio.run(media_insights({"media_id": "M1"}))
    assert out["insights"]["object_id"] == "M1"
    assert out["auth_mode"] == "none"
    assert out["error"] is None


# ─── meta.diagnostics.connection_status ──────────────────────────────────


def test_connection_status_reports_fake_adapter_and_auth_mode_none():
    from meta.tools.diagnostics import connection_status

    out = asyncio.run(connection_status({}))
    assert out["configured"] is False
    assert out["adapter"] == "fake"
    assert out["auth_mode"] == "none"
    assert out["pages_count"] == 0
    assert out["instagram_accounts_count"] == 0
    assert out["error"] is None


# ─── meta.diagnostics.discover_scopes — the source branches ──────────────


def test_discover_scopes_explicit_list_used_verbatim():
    from meta.tools.diagnostics import discover_scopes

    out = asyncio.run(
        discover_scopes({"configured_scopes": "pages_show_list,read_insights"})
    )
    assert out["scopes"] == ["pages_show_list", "read_insights"]
    assert out["source"] == "explicit"
    assert out["error"] is None


def test_discover_scopes_auto_no_creds_falls_back_to_kitchen_sink():
    from meta.tools.diagnostics import discover_scopes
    from noctusai_lib.integrations.meta import META_KITCHEN_SINK_SCOPES

    out = asyncio.run(discover_scopes({"configured_scopes": "auto"}))
    assert out["scopes"] == list(META_KITCHEN_SINK_SCOPES)
    assert out["source"] == "kitchen_sink"
    assert out["error"] is None


def test_discover_scopes_empty_input_also_kitchen_sink():
    from meta.tools.diagnostics import discover_scopes
    from noctusai_lib.integrations.meta import META_KITCHEN_SINK_SCOPES

    out = asyncio.run(discover_scopes({}))
    assert out["scopes"] == list(META_KITCHEN_SINK_SCOPES)
    assert out["source"] == "kitchen_sink"


# ─── Mappers driven by a seeded FakeMetaAdapter (real code, no patch) ────


def test_facebook_mappers_against_seeded_fake_adapter():
    from meta.tools.facebook import _page_out, _post_out
    from noctusai_lib.integrations.meta import FakeMetaAdapter
    from noctusai_lib.integrations.meta.types import FacebookPage, FacebookPost

    page = FacebookPage(
        id="P1",
        name="One Consultoria",
        category="Business",
        access_token="SECRET-TOKEN-DO-NOT-LEAK",
        fan_count=1200,
        followers_count=1300,
        link="https://fb.com/onec",
        tasks=["MANAGE", "CREATE_CONTENT"],
    )
    when = datetime(2026, 5, 16, 12, 30, 0)
    post = FacebookPost(
        id="POST_1",
        message="hello world",
        created_time=when,
        permalink_url="https://fb.com/onec/posts/1",
        likes=10,
        comments=3,
        shares=2,
    )
    fake = FakeMetaAdapter().seed(
        pages=[page], posts_by_page={"P1": [post]}
    )

    pages = fake.list_facebook_pages()
    po = _page_out(pages[0])
    assert po.id == "P1"
    assert po.name == "One Consultoria"
    assert po.tasks == ["MANAGE", "CREATE_CONTENT"]
    # The per-Page access_token must NEVER appear on the wire shape.
    assert "access_token" not in po.model_dump()

    posts = fake.list_facebook_posts("P1")
    out = _post_out(posts[0])
    assert out.id == "POST_1"
    assert out.created_time == when.isoformat()
    assert out.likes == 10 and out.comments == 3 and out.shares == 2


def test_instagram_mappers_against_seeded_fake_adapter():
    from meta.tools.instagram import _account_out, _media_out
    from noctusai_lib.integrations.meta import FakeMetaAdapter
    from noctusai_lib.integrations.meta.types import (
        InstagramAccount,
        InstagramMedia,
    )

    acct = InstagramAccount(
        id="IG1",
        username="onec",
        name="One Consultoria",
        followers_count=900,
        media_count=42,
        page_id="P1",
    )
    when = datetime(2026, 5, 15, 9, 0, 0)
    media = InstagramMedia(
        id="M1",
        caption="a reel",
        media_type="VIDEO",
        permalink="https://instagram.com/p/abc",
        timestamp=when,
        like_count=55,
        comments_count=4,
    )
    fake = FakeMetaAdapter().seed(
        ig_accounts=[acct], media_by_ig_user={"IG1": [media]}
    )

    ao = _account_out(fake.list_instagram_accounts()[0])
    assert ao.id == "IG1"
    assert ao.username == "onec"
    assert ao.page_id == "P1"

    mo = _media_out(fake.list_instagram_media("IG1")[0])
    assert mo.id == "M1"
    assert mo.media_type == "VIDEO"
    assert mo.timestamp == when.isoformat()
    assert mo.like_count == 55 and mo.comments_count == 4


# ─── Typed-error enrichment shape (Meta branchable signals) ──────────────


def test_meta_error_envelope_surfaces_branchable_signals():
    """`MetaGraphError` carries `.http_status` (not `.status`); the
    leaf `_meta_error` enrichment exposes http_status / is_auth_error /
    is_rate_limited so the host LLM can branch deterministically even
    though `_kit.errors.typed_error` only probes `.status`."""
    from meta.tools.facebook import _meta_error
    from noctusai_lib.integrations.meta import MetaGraphError

    e = MetaGraphError(
        "Invalid OAuth access token", code=190, http_status=401
    )
    env = _meta_error(e)
    assert env["error_class"] == "MetaGraphError"
    assert env["status"] is None  # _kit probes .status — absent here
    assert env["http_status"] == 401
    assert env["is_auth_error"] is True
    assert env["is_rate_limited"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
