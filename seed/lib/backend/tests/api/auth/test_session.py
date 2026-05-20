"""Tests for ``noctusai_lib.api.auth.session``.

Covers Wave-1 scaffolding (Fakes + dep factory). Real-adapter tests
land with the Wave-2 ``E-SW-AUTH`` project.

Status-code-assertion rule: every body assertion is paired with a
``.status_code`` assertion in the same test (``KB § PATTERNS/testing.md``).
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.api.auth.session import (
    AuthContext,
    FakeApiTokenResolver,
    FakeSessionStore,
    hash_token,
    make_get_auth_context,
)


# ── helpers ──────────────────────────────────────────────────────────


def _run(coro):
    """Run a coroutine synchronously from a sync test body."""
    return asyncio.new_event_loop().run_until_complete(coro)


def _build_app(
    *,
    session_store: FakeSessionStore | None = None,
    api_token_resolver: FakeApiTokenResolver | None = None,
    legacy_jwt_resolver=None,
) -> tuple[FastAPI, FakeSessionStore, FakeApiTokenResolver]:
    store = session_store or FakeSessionStore()
    resolver = api_token_resolver or FakeApiTokenResolver()
    dep = make_get_auth_context(
        session_store=store,
        api_token_resolver=resolver,
        legacy_jwt_resolver=legacy_jwt_resolver,
    )
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(ctx: AuthContext = Depends(dep)):
        return {
            "org_id": str(ctx.org_id),
            "caller_kind": ctx.caller_kind,
            "user_id": str(ctx.user_id) if ctx.user_id else None,
            "api_token_id": str(ctx.api_token_id) if ctx.api_token_id else None,
            "scopes": list(ctx.scopes),
            "raw_token": ctx.raw_token,
        }

    return app, store, resolver


# ── AuthContext shape ────────────────────────────────────────────────


def test_auth_context_is_named_tuple_with_expected_fields():
    """AuthContext exposes the six contract fields as a NamedTuple."""
    org_id = uuid4()
    user_id = uuid4()
    ctx = AuthContext(
        org_id=org_id,
        caller_kind="user",
        user_id=user_id,
        scopes=["read"],
        raw_token="session-id-x",
        api_token_id=None,
    )

    # NamedTuple identity — positional + by-field equality.
    assert ctx.org_id == org_id
    assert ctx.caller_kind == "user"
    assert ctx.user_id == user_id
    assert ctx.scopes == ["read"]
    assert ctx.raw_token == "session-id-x"
    assert ctx.api_token_id is None
    # NamedTuple equality (different instance, same fields → ==).
    assert ctx == AuthContext(
        org_id=org_id,
        caller_kind="user",
        user_id=user_id,
        scopes=["read"],
        raw_token="session-id-x",
        api_token_id=None,
    )


# ── hash_token ────────────────────────────────────────────────────────


def test_hash_token_is_sha256_hex():
    """hash_token returns the SHA-256 hex digest of the UTF-8-encoded secret."""
    secret = "pk_abc123"
    assert hash_token(secret) == hashlib.sha256(secret.encode("utf-8")).hexdigest()


def test_hash_token_is_deterministic():
    """Repeated calls with the same input → identical digest."""
    assert hash_token("pk_xyz") == hash_token("pk_xyz")
    assert hash_token("pk_xyz") != hash_token("pk_zzz")


# ── FakeSessionStore ─────────────────────────────────────────────────


def test_session_store_create_then_lookup_returns_user_ctx():
    """create returns an opaque session_id; lookup yields the AuthContext."""
    store = FakeSessionStore()
    user_id = uuid4()
    org_id = uuid4()

    session_id = _run(
        store.create(
            user_id=user_id,
            org_id=org_id,
            supabase_refresh_token="rt-xxx",
            ttl_seconds=60,
        )
    )
    assert isinstance(session_id, str)
    assert len(session_id) >= 32  # token_urlsafe(32) yields ~43 chars

    ctx = _run(store.lookup(session_id))
    assert ctx is not None
    assert ctx.caller_kind == "user"
    assert ctx.user_id == user_id
    assert ctx.org_id == org_id
    assert ctx.api_token_id is None
    assert ctx.raw_token == session_id


def test_session_store_delete_makes_lookup_return_none():
    """delete is hard-delete; subsequent lookup returns None."""
    store = FakeSessionStore()
    session_id = _run(
        store.create(
            user_id=uuid4(),
            org_id=uuid4(),
            supabase_refresh_token="rt",
            ttl_seconds=60,
        )
    )
    _run(store.delete(session_id))
    assert _run(store.lookup(session_id)) is None


def test_session_store_expired_lookup_returns_none():
    """TTL is honoured against time.monotonic; expired entries → None."""
    store = FakeSessionStore()
    session_id = _run(
        store.create(
            user_id=uuid4(),
            org_id=uuid4(),
            supabase_refresh_token="rt",
            ttl_seconds=60,
        )
    )
    # Advance the monotonic clock past the TTL — the store reads
    # time.monotonic() directly, so monkeypatching is the right seam.
    with _patched_monotonic(offset_seconds=120):
        assert _run(store.lookup(session_id)) is None


def test_session_store_refresh_ttl_extends_expiry():
    """refresh_ttl resets the clock; an otherwise-expired session lives."""
    store = FakeSessionStore()
    session_id = _run(
        store.create(
            user_id=uuid4(),
            org_id=uuid4(),
            supabase_refresh_token="rt",
            ttl_seconds=60,
        )
    )
    with _patched_monotonic(offset_seconds=30):
        # 30s in — still alive, refresh extends.
        _run(store.refresh_ttl(session_id, ttl_seconds=600))
    with _patched_monotonic(offset_seconds=120):
        # Original TTL would have expired; refreshed TTL (600s) keeps it.
        ctx = _run(store.lookup(session_id))
        assert ctx is not None


# ── FakeApiTokenResolver ──────────────────────────────────────────────


def test_api_token_resolver_resolves_registered_token():
    """register + resolve roundtrips to a product AuthContext."""
    resolver = FakeApiTokenResolver()
    org_id = uuid4()
    token_id = resolver.register(
        "pk_secret_xxx", org_id=org_id, scopes=["posts:read"]
    )

    ctx = _run(resolver.resolve("pk_secret_xxx"))
    assert ctx is not None
    assert ctx.caller_kind == "product"
    assert ctx.org_id == org_id
    assert ctx.user_id is None
    assert ctx.api_token_id == token_id
    assert ctx.scopes == ["posts:read"]


def test_api_token_resolver_returns_none_for_unknown_secret():
    """A secret never registered → None (not an exception)."""
    resolver = FakeApiTokenResolver()
    assert _run(resolver.resolve("pk_never_minted")) is None


def test_api_token_resolver_revoked_token_returns_none():
    """revoke marks the row; resolve returns None thereafter."""
    resolver = FakeApiTokenResolver()
    resolver.register("pk_revoke_me", org_id=uuid4(), scopes=[])
    assert _run(resolver.resolve("pk_revoke_me")) is not None

    resolver.revoke("pk_revoke_me")
    assert _run(resolver.resolve("pk_revoke_me")) is None


# ── make_get_auth_context — dep behaviour ─────────────────────────────


def test_dep_returns_user_ctx_when_cookie_present():
    """Cookie-only request → user AuthContext (priority 1)."""
    app, store, _resolver = _build_app()
    user_id = uuid4()
    org_id = uuid4()
    session_id = _run(
        store.create(
            user_id=user_id,
            org_id=org_id,
            supabase_refresh_token="rt",
            ttl_seconds=60,
        )
    )
    client = TestClient(app)

    resp = client.get("/whoami", cookies={"nai_session": session_id})

    assert resp.status_code == 200
    body = resp.json()
    assert body["caller_kind"] == "user"
    assert body["user_id"] == str(user_id)
    assert body["org_id"] == str(org_id)
    assert body["api_token_id"] is None


def test_dep_returns_product_ctx_when_bearer_pk_token():
    """Bearer pk_* → product AuthContext (priority 2)."""
    app, _store, resolver = _build_app()
    org_id = uuid4()
    token_id = resolver.register(
        "pk_live_zzz", org_id=org_id, scopes=["posts:write"]
    )
    client = TestClient(app)

    resp = client.get(
        "/whoami", headers={"Authorization": "Bearer pk_live_zzz"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["caller_kind"] == "product"
    assert body["user_id"] is None
    assert body["api_token_id"] == str(token_id)
    assert body["org_id"] == str(org_id)
    assert body["scopes"] == ["posts:write"]


def test_dep_cookie_wins_when_both_cookie_and_bearer_present():
    """Cookie + Bearer same request → cookie resolves (priority 1 > 2)."""
    app, store, resolver = _build_app()
    user_id = uuid4()
    user_org = uuid4()
    session_id = _run(
        store.create(
            user_id=user_id,
            org_id=user_org,
            supabase_refresh_token="rt",
            ttl_seconds=60,
        )
    )
    resolver.register("pk_other_org", org_id=uuid4(), scopes=[])
    client = TestClient(app)

    resp = client.get(
        "/whoami",
        cookies={"nai_session": session_id},
        headers={"Authorization": "Bearer pk_other_org"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["caller_kind"] == "user"
    assert body["org_id"] == str(user_org)  # NOT the bearer's org


def test_dep_returns_401_when_no_credential():
    """No cookie + no Authorization → 401."""
    app, _store, _resolver = _build_app()
    client = TestClient(app)

    resp = client.get("/whoami")

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


def test_dep_returns_401_for_unknown_pk_bearer():
    """Bearer pk_ that doesn't resolve → 401 with token-specific detail."""
    app, _store, _resolver = _build_app()
    client = TestClient(app)

    resp = client.get(
        "/whoami", headers={"Authorization": "Bearer pk_unknown"}
    )

    assert resp.status_code == 401
    assert "API token" in resp.json()["detail"]


def test_dep_returns_401_for_expired_cookie():
    """Cookie present but unrecognised → 401 (do NOT fall through to bearer)."""
    app, _store, _resolver = _build_app()
    client = TestClient(app)

    resp = client.get(
        "/whoami", cookies={"nai_session": "never-existed-session-id"}
    )

    assert resp.status_code == 401
    assert "Session" in resp.json()["detail"]


def test_dep_bridges_jwt_through_legacy_resolver():
    """Bearer <jwt> AND legacy_jwt_resolver wired → resolver decides."""
    bridge_org = uuid4()

    async def legacy(token: str) -> AuthContext | None:
        if token == "valid.jwt.payload":
            return AuthContext(
                org_id=bridge_org,
                caller_kind="user",
                user_id=uuid4(),
                scopes=["legacy"],
                raw_token=token,
                api_token_id=None,
            )
        return None

    app, _store, _resolver = _build_app(legacy_jwt_resolver=legacy)
    client = TestClient(app)

    resp = client.get(
        "/whoami", headers={"Authorization": "Bearer valid.jwt.payload"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["org_id"] == str(bridge_org)
    assert body["scopes"] == ["legacy"]


def test_dep_returns_401_for_bearer_jwt_without_bridge():
    """Bearer <jwt> AND no legacy_jwt_resolver → 401."""
    app, _store, _resolver = _build_app()  # no legacy bridge
    client = TestClient(app)

    resp = client.get(
        "/whoami", headers={"Authorization": "Bearer some.jwt.value"}
    )

    assert resp.status_code == 401
    assert "Bearer" in resp.json()["detail"]


# ── time.monotonic patch helper ──────────────────────────────────────


class _patched_monotonic:
    """Context manager that advances ``time.monotonic`` by ``offset_seconds``.

    Patching ``time.monotonic`` is the only viable seam in v1 — the
    Fake reads it directly and v1 deliberately doesn't expose a clock-
    injection parameter (the entire monotonic clock is process-local).
    Test-only; production code never touches this attribute.
    """

    def __init__(self, offset_seconds: float) -> None:
        self.offset = offset_seconds
        self._patcher = None

    def __enter__(self):
        from unittest.mock import patch

        baseline = time.monotonic()
        self._patcher = patch(
            "noctusai_lib.api.auth.session.store.time.monotonic",
            new=lambda: baseline + self.offset,
        )
        self._patcher.start()
        return self

    def __exit__(self, *exc):
        assert self._patcher is not None
        self._patcher.stop()
        return False
