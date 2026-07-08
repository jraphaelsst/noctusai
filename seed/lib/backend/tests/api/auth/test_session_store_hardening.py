"""Hardening tests for the auth-session store (SEC-2 + SEC-3).

Covers the 2026-07-08 hardening of ``RedisSessionStore`` /
``FakeSessionStore``:

- SEC-3 — refresh + access tokens encrypted at rest; ``enc`` flag; key
  rotation via ``extra_decrypt_keys``; loud failure when a store loses its
  key; the ``require_encryption`` factory guard.
- SEC-2 — ``read_tokens`` / ``write_tokens`` server-side accessors; access
  token cache; rotated refresh token written back; TTL preserved across a
  token write; absent-session no-op.

Uses ``fakeredis.aioredis.FakeRedis`` (no live Redis). Each test drives all
its work inside a single coroutine (fakeredis binds to the first loop it is
used in) via ``_run``.
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import fakeredis.aioredis
import pytest

from noctusai_lib.api.auth.session import (
    FakeSessionStore,
    RedisSessionStore,
    SessionTokens,
    make_session_store,
)
from noctusai_lib.security.encrypted_tokens import generate_key


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _client():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


# ── SEC-3: encryption at rest ────────────────────────────────────────


def test_refresh_token_encrypted_at_rest_but_readable_via_read_tokens():
    async def _t():
        key = generate_key()
        client = _client()
        store = RedisSessionStore(client=client, encryption_key=key)
        assert store.encrypts_at_rest is True
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="the-secret-rt"
        )
        # Raw Redis bytes must NOT contain the plaintext refresh token.
        raw = await client.get(store._key(sid))
        assert "the-secret-rt" not in raw
        record = json.loads(raw)
        assert record["enc"] is True
        assert record["refresh_token"] != "the-secret-rt"
        # ...but read_tokens decrypts it back.
        tokens = await store.read_tokens(sid)
        assert tokens == SessionTokens(
            refresh_token="the-secret-rt", access_token=None, access_expires_at=None
        )

    _run(_t())


def test_plaintext_store_marks_enc_false_and_roundtrips():
    async def _t():
        store = RedisSessionStore(client=_client())  # no key
        assert store.encrypts_at_rest is False
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt-plain"
        )
        raw = await store._get_client().get(store._key(sid))
        assert json.loads(raw)["enc"] is False
        tokens = await store.read_tokens(sid)
        assert tokens.refresh_token == "rt-plain"

    _run(_t())


def test_encrypted_row_readable_after_key_rotation():
    async def _t():
        old_key, new_key = generate_key(), generate_key()
        client = _client()
        # Row written with old_key...
        writer = RedisSessionStore(client=client, encryption_key=old_key)
        sid = await writer.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rotated-rt"
        )
        # ...read by a store whose current key is new_key but that still
        # accepts old_key on the read path.
        reader = RedisSessionStore(
            client=client, encryption_key=new_key, extra_decrypt_keys=[old_key]
        )
        tokens = await reader.read_tokens(sid)
        assert tokens.refresh_token == "rotated-rt"

    _run(_t())


def test_encrypted_row_without_key_fails_loud():
    async def _t():
        key = generate_key()
        client = _client()
        enc_store = RedisSessionStore(client=client, encryption_key=key)
        sid = await enc_store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt"
        )
        # A store that lost its key must NOT hand back ciphertext as a token.
        plain_store = RedisSessionStore(client=client)
        with pytest.raises(ValueError):
            await plain_store.read_tokens(sid)

    _run(_t())


def test_access_token_also_encrypted_at_rest():
    async def _t():
        key = generate_key()
        client = _client()
        store = RedisSessionStore(client=client, encryption_key=key)
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt"
        )
        await store.write_tokens(
            sid,
            refresh_token="rt2",
            access_token="access-secret-123",
            access_expires_at=9999999999,
        )
        raw = await client.get(store._key(sid))
        assert "access-secret-123" not in raw
        assert "rt2" not in raw
        tokens = await store.read_tokens(sid)
        assert tokens.access_token == "access-secret-123"
        assert tokens.refresh_token == "rt2"

    _run(_t())


# ── SEC-2: read_tokens / write_tokens ────────────────────────────────


def test_read_tokens_absent_returns_none():
    async def _t():
        store = RedisSessionStore(client=_client())
        assert await store.read_tokens("nope") is None

    _run(_t())


def test_write_tokens_caches_access_and_rotates_refresh():
    async def _t():
        store = RedisSessionStore(client=_client())
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt0"
        )
        await store.write_tokens(
            sid, refresh_token="rt1", access_token="at1", access_expires_at=123456
        )
        tokens = await store.read_tokens(sid)
        assert tokens == SessionTokens(
            refresh_token="rt1", access_token="at1", access_expires_at=123456
        )

    _run(_t())


def test_write_tokens_preserves_ttl():
    async def _t():
        store = RedisSessionStore(client=_client())
        client = store._get_client()
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt",
            ttl_seconds=3600,
        )
        before = await client.ttl(store._key(sid))
        assert before > 0
        await store.write_tokens(
            sid, refresh_token="rt2", access_token="at", access_expires_at=1
        )
        after = await client.ttl(store._key(sid))
        # keepttl — the absolute expiry must not be dropped or reset to -1.
        assert after > 0

    _run(_t())


def test_write_tokens_absent_session_is_noop_no_resurrect():
    async def _t():
        store = RedisSessionStore(client=_client())
        await store.write_tokens(
            "ghost", refresh_token="rt", access_token="at", access_expires_at=1
        )
        # Must NOT have created a key for a non-existent session.
        assert await store.read_tokens("ghost") is None

    _run(_t())


def test_lookup_still_hides_tokens_after_write():
    async def _t():
        store = RedisSessionStore(client=_client())
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt0"
        )
        await store.write_tokens(
            sid, refresh_token="rt1", access_token="super-access", access_expires_at=1
        )
        ctx = await store.lookup(sid)
        assert ctx is not None
        assert "super-access" not in str(ctx)
        assert "rt1" not in str(ctx)

    _run(_t())


# ── FakeSessionStore parity ──────────────────────────────────────────


def test_fake_store_read_write_tokens_parity():
    async def _t():
        store = FakeSessionStore()
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt0"
        )
        assert await store.read_tokens(sid) == SessionTokens(
            refresh_token="rt0", access_token=None, access_expires_at=None
        )
        await store.write_tokens(
            sid, refresh_token="rt1", access_token="at1", access_expires_at=42
        )
        assert await store.read_tokens(sid) == SessionTokens(
            refresh_token="rt1", access_token="at1", access_expires_at=42
        )
        # Cache write must not clobber the caller-facing context.
        assert (await store.lookup(sid)) is not None

    _run(_t())


def test_fake_store_write_tokens_absent_is_noop():
    async def _t():
        store = FakeSessionStore()
        await store.write_tokens(
            "ghost", refresh_token="rt", access_token="at", access_expires_at=1
        )
        assert await store.read_tokens("ghost") is None

    _run(_t())


# ── factory: require_encryption guard (SEC-3) ────────────────────────


def test_factory_require_encryption_without_key_raises():
    with pytest.raises(ValueError):
        make_session_store(
            "redis://localhost:6379/0", require_encryption=True
        )
    with pytest.raises(ValueError):
        make_session_store(
            None, client=_client(), require_encryption=True
        )


def test_factory_encryption_key_builds_encrypting_store():
    store = make_session_store(
        None, client=_client(), encryption_key=generate_key()
    )
    assert isinstance(store, RedisSessionStore)
    assert store.encrypts_at_rest is True


def test_factory_require_encryption_allows_fake_without_key():
    # No Redis ⇒ Fake ⇒ no plaintext-in-shared-Redis risk ⇒ guard doesn't fire.
    store = make_session_store(None, require_encryption=True)
    assert isinstance(store, FakeSessionStore)
