"""Tests for the ``SessionRevoker`` (SEC-4 upstream logout revoke).

The real GoTrue sign-out is a prod-shape false-green in unit tests (no live
Supabase), so the SEC-1 revoke_fn is injected as a fake here; the real
throwaway-anon-client path is verified in prod shape (Slice 4). What IS unit
-tested: the best-effort-but-logged contract (never raises into logout),
success/failure signalling, the empty-token no-op, and factory selection.
"""

from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.api.auth.session import (
    FakeSessionRevoker,
    SupabaseSessionRevoker,
    make_session_revoker,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── FakeSessionRevoker ───────────────────────────────────────────────


def test_fake_records_and_succeeds():
    async def _t():
        r = FakeSessionRevoker()
        assert await r.revoke("rt-1") is True
        assert await r.revoke("rt-2") is True
        assert r.revoked == ["rt-1", "rt-2"]

    _run(_t())


def test_fake_can_simulate_failure():
    async def _t():
        r = FakeSessionRevoker(succeed=False)
        assert await r.revoke("rt") is False
        assert r.revoked == ["rt"]  # still recorded the attempt

    _run(_t())


# ── SupabaseSessionRevoker — best-effort-but-logged ──────────────────


def test_real_success_calls_revoke_fn_once():
    async def _t():
        calls = []
        r = SupabaseSessionRevoker(lambda rt: calls.append(rt))
        assert await r.revoke("rt-x") is True
        assert calls == ["rt-x"]

    _run(_t())


def test_real_failure_is_logged_not_raised():
    """SEC-4: an upstream failure must NOT raise — logout still proceeds."""

    async def _t():
        def boom(rt):
            raise ConnectionError("supabase unreachable")

        r = SupabaseSessionRevoker(boom)
        # Must return False, never raise.
        assert await r.revoke("rt") is False

    _run(_t())


def test_real_empty_token_is_noop_success():
    async def _t():
        calls = []
        r = SupabaseSessionRevoker(lambda rt: calls.append(rt))
        assert await r.revoke("") is True
        assert calls == []  # nothing to revoke → revoke_fn not called

    _run(_t())


# ── factory ──────────────────────────────────────────────────────────


def test_factory_no_config_returns_fake():
    assert isinstance(make_session_revoker(), FakeSessionRevoker)


def test_factory_revoke_fn_returns_real():
    r = make_session_revoker(revoke_fn=lambda rt: None)
    assert isinstance(r, SupabaseSessionRevoker)


def test_factory_supabase_creds_returns_real():
    r = make_session_revoker(
        supabase_url="https://x.supabase.co", supabase_anon_key="anon"
    )
    assert isinstance(r, SupabaseSessionRevoker)
