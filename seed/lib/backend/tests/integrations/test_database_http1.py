"""PostgREST is forced onto HTTP/1.1 — the fix for a reproduced outage.

`postgrest` hardcodes `http2=True`, httpx's SYNC HTTP/2 transport is not safe
to share across threads, and FastAPI runs every non-async endpoint in a
threadpool against ONE cached client. Measured against the live PostgREST,
8 concurrent threads: http2 → 3 ok / 5 errors; http1 → 8 ok / 0 errors.

These tests pin the mechanism, not the network: that the session really is
replaced, that it is replaced exactly once, and — the part that matters most
— that a future `postgrest` whose shape changed leaves a WORKING client and a
LOUD warning rather than a silent regression back onto HTTP/2.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import httpx
import pytest

from noctusai_lib.integrations.database import force_postgrest_http1


class _Session:
    """Stands in for postgrest's `httpx.Client`."""

    def __init__(self):
        self.base_url = httpx.URL("https://example.supabase.co/rest/v1/")
        self.headers = httpx.Headers({"apikey": "k"})
        self.timeout = httpx.Timeout(5.0)
        self.closed = False

    def close(self):
        self.closed = True


def _client():
    return SimpleNamespace(postgrest=SimpleNamespace(session=_Session()))


class TestTheSwap:
    def test_the_session_is_replaced_with_an_http1_client(self):
        c = _client()
        original = c.postgrest.session
        force_postgrest_http1(c)
        assert c.postgrest.session is not original
        assert isinstance(c.postgrest.session, httpx.Client)

    def test_it_carries_the_original_connection_settings_over(self):
        """A replacement that lost the base URL or the apikey header would
        turn a thread-safety fix into a total outage."""
        c = _client()
        before = c.postgrest.session
        force_postgrest_http1(c)
        after = c.postgrest.session
        assert after.base_url == before.base_url
        assert after.headers["apikey"] == "k"

    def test_the_old_pool_is_closed_but_only_after_the_swap(self):
        c = _client()
        original = c.postgrest.session
        force_postgrest_http1(c)
        assert original.closed is True
        assert c.postgrest.session is not original

    def test_it_is_idempotent(self):
        """🔴 A second call must not build a second pool. Client construction
        is on a cached path, but nothing stops a caller re-invoking it."""
        c = _client()
        force_postgrest_http1(c)
        first = c.postgrest.session
        force_postgrest_http1(c)
        assert c.postgrest.session is first


class TestItNeverFailsSilently:
    """🔴 The failure mode that would matter: a future postgrest changes
    shape, the patch stops applying, and prod quietly returns to the broken
    HTTP/2 behaviour with nothing to find."""

    def test_a_client_with_no_postgrest_is_returned_working_and_warned_about(
        self, caplog
    ):
        c = SimpleNamespace()
        with caplog.at_level(logging.WARNING):
            out = force_postgrest_http1(c)
        assert out is c
        assert any("NOT mitigated" in r.getMessage() for r in caplog.records)

    def test_a_session_that_cannot_be_replaced_warns_and_keeps_working(
        self, caplog, monkeypatch
    ):
        c = _client()
        original = c.postgrest.session

        def _boom(*a, **k):
            raise RuntimeError("no transport")

        monkeypatch.setattr(httpx, "Client", _boom)
        with caplog.at_level(logging.WARNING):
            out = force_postgrest_http1(c)

        assert out is c
        # 🔴 The ORIGINAL session survives — a half-applied patch that closed
        # the old pool without installing a new one would be worse than the
        # bug it was fixing.
        assert c.postgrest.session is original
        assert original.closed is False
        assert any("NOT mitigated" in r.getMessage() for r in caplog.records)

    def test_a_pool_that_refuses_to_close_does_not_break_the_client(self):
        """The replacement is already installed by then; a socket that leaks
        is not a reason to raise into client construction."""
        c = _client()

        def _bad_close():
            raise OSError("already gone")

        c.postgrest.session.close = _bad_close
        out = force_postgrest_http1(c)
        assert isinstance(out.postgrest.session, httpx.Client)


class TestTheResultReallyIsHttp1:
    def test_http2_is_disabled_on_the_replacement(self):
        """The whole point. Asserted through httpx's own transport rather
        than a flag we set ourselves."""
        c = _client()
        force_postgrest_http1(c)
        transport = c.postgrest.session._transport_for_url(
            httpx.URL("https://example.supabase.co/rest/v1/x")
        )
        assert transport._pool._http2 is False
