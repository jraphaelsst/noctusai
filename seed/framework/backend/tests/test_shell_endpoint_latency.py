"""Shell endpoints every page calls (``/api/me/access``, ``/api/notificacoes*``): pin the MECHANISM
of their latency, not a wall-clock number -- PostgREST round trips per request, the independent
reads running concurrently, and the handlers' DB work off the event loop.
KB § PATTERNS/backend/request-path-latency.md"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import Counter
from types import SimpleNamespace
from typing import Optional

import httpx
import pytest
from fastapi import FastAPI, Header

from noctusai_lib.api.auth._blocking import run_blocking, run_parallel
from noctusai_lib.domain.licensing import configure_license_gate
from noctusai_lib.testing import MockSupabaseClient
from noctusai_lib.testing._schema_cache import get_foreign_key_map, get_schema_map
from noctusai_seed.routers import _create_notificacoes_router

from tests.test_org_picker_router import CLIENT_A, HOME, OWNER, SLUG, STAFF, _h, _make

HOP = 0.15


@pytest.fixture(autouse=True, scope="module")
def _mock_caches_built():
    """The mock parses the migrations (columns, foreign keys) on first use; build both up front
    so that one-off cost never lands inside a timed request."""
    get_schema_map()
    get_foreign_key_map()


class _CountingCore:
    """Delegates to a MockSupabaseClient, counting ``.table()`` calls per table (= PostgREST
    round trips, each one HTTP request in production)."""

    def __init__(self, inner, delay: float = 0.0):
        self._inner, self.calls, self._delay = inner, Counter(), delay
        self._lock = threading.Lock()

    def table(self, name):
        with self._lock:
            self.calls[name] += 1
        if self._delay:
            time.sleep(self._delay)
        return self._inner.table(name)

    def __getattr__(self, item):
        return getattr(self._inner, item)


class TestRunParallel:
    def test_overlaps_and_keeps_argument_order(self):
        def slow(v):
            def run():
                time.sleep(0.15)
                return v
            return run

        t0 = time.monotonic()
        out = run_parallel(slow(1), slow(2), slow(3))
        assert out == [1, 2, 3]
        assert time.monotonic() - t0 < 0.4  # serial would be >= 0.45

    def test_every_thunk_finishes_then_first_exception_by_order_is_raised(self):
        done = []

        def boom():
            raise ValueError("first")

        def late():
            time.sleep(0.1)
            done.append(1)

        with pytest.raises(ValueError, match="first"):
            run_parallel(boom, late)
        assert done == [1]  # nothing left running behind the raise


class TestMeAccessRoundTrips:
    def test_member_access_is_a_handful_of_calls_not_a_dozen(self):
        client, _store = _make()
        counting = _swap_core(client)
        resp = client.get("/api/me/access", headers=_h(OWNER))
        assert resp.status_code == 200
        body = resp.json()
        assert body["org_selection"]["org"]["nome"] == "Zeta Imob"
        assert body["org_selection"]["manageable_orgs"][0]["id"] == CLIENT_A
        # noctus_users: resolve + the named profile; org_memberships: the named memberships. Every
        # org name and the staff rule's is_platform ride along as embeds: NO organizations read.
        assert counting.calls["noctus_users"] == 2
        assert counting.calls["organizations"] == 0
        assert counting.calls["org_memberships"] == 1
        assert sum(counting.calls.values()) <= 3

    def test_staff_access_names_the_home_org_without_a_lookup(self):
        client, _store = _make()
        counting = _swap_core(client)
        resp = client.get("/api/me/access", headers=_h(STAFF))
        assert resp.status_code == 200
        block = resp.json()["org_selection"]
        assert block["platform_role"] == "owner" and block["manage_any_org"] is True
        assert block["home_org"] == {"id": HOME, "nome": "NoctusAI"}
        assert counting.calls["organizations"] == 0

    def test_every_read_is_issued_together_one_round_trip(self):
        client, _store = _make()
        counting = _swap_core(client)
        counting._delay = HOP
        t0 = time.monotonic()
        assert client.get("/api/me/access", headers=_h(OWNER)).status_code == 200
        assert time.monotonic() - t0 < 1.8 * HOP  # names after the reads = 2 hops; staff probe = 3


def _swap_core(client) -> _CountingCore:
    """Replace the core the me-router + license gate use with a counting wrapper (the router
    reads ``deps.get_core_client`` per request, so swapping the MockSupabaseClient's holder works)."""
    from noctusai_lib.domain.licensing import get_license_gate

    inner = get_license_gate().get_core_client()
    counting = _CountingCore(inner)
    for route in client.app.routes:
        endpoint = getattr(route, "endpoint", None)
        closure = getattr(endpoint, "__closure__", None) or ()
        for cell in closure:
            val = cell.cell_contents
            if hasattr(val, "get_core_client"):
                val.get_core_client = lambda: counting
    gate = get_license_gate()
    configure_license_gate(
        gate.product_slug, gate.checker, selection_store=gate.selection_store,
        db_schema="igig", get_core_client=lambda: counting,
    )
    return counting


class TestNotificacoesOffTheLoop:
    def test_two_concurrent_requests_overlap_instead_of_serializing(self):
        inner = MockSupabaseClient()
        inner.table("notifications").select("id", count="exact").execute()  # one-off mock warm-up
        core = _CountingCore(inner, delay=0.2)

        async def get_current_user(authorization: Optional[str] = Header(None)):
            return SimpleNamespace(id="u1"), "tok"

        async def get_current_user_and_fetch(authorization, fetch):
            user, token = await get_current_user(authorization)
            return user, token, await run_blocking(fetch, user)

        deps = SimpleNamespace(
            get_core_client=lambda: core, get_current_user=get_current_user,
            get_current_user_and_fetch=get_current_user_and_fetch,
        )
        app = FastAPI()
        app.include_router(_create_notificacoes_router(deps))

        async def run():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
                t0 = time.monotonic()
                rs = await asyncio.gather(*(c.get("/api/notificacoes/contagem") for _ in range(4)))
                return rs, time.monotonic() - t0

        rs, elapsed = asyncio.run(run())
        assert [r.status_code for r in rs] == [200] * 4
        assert core.calls["notifications"] == 4
        assert elapsed < 0.6  # four 0.2 s calls serialized on the loop would be >= 0.8
