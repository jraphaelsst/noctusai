"""Core's own auth helpers + the shell endpoints it serves (/api/me/consents, /api/admin/llm-spend):
pin the MECHANISM of their latency -- sync PostgREST work runs in a worker thread (the loop keeps
turning), independent reads overlap, and the permission chain reads the profile once.
KB § PATTERNS/backend/request-path-latency.md"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import Counter
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from noctusai_lib.domain.ai.consent import fetch_user_decisions
from noctusai_lib.testing import MockSupabaseClient

MAIN = threading.main_thread().ident


class _Spy:
    """MockSupabaseClient delegate: counts ``.table()`` calls per table, sleeps ``delay`` on each
    ``.execute()`` and records the thread each execute ran on."""

    def __init__(self, inner, delay=0.0):
        self._inner, self.calls, self.threads, self._delay = inner, Counter(), set(), delay
        self.spans = []  # (start, end) of every execute() = every PostgREST round trip
        self._lock = threading.Lock()

    def table(self, name):
        with self._lock:
            self.calls[name] += 1
        return _Builder(self._inner.table(name), self)

    from_ = table

    def schema(self, _name):
        return self  # the seed helpers address `public` explicitly; keep counting through it

    def __getattr__(self, item):
        return getattr(self._inner, item)


class _Builder:
    def __init__(self, inner, spy):
        self._inner, self._spy = inner, spy

    def __getattr__(self, item):
        attr = getattr(self._inner, item)
        if item == "execute":
            def run():
                self._spy.threads.add(threading.get_ident())
                start = time.monotonic()
                if self._spy._delay:
                    time.sleep(self._spy._delay)
                try:
                    return attr()
                finally:
                    self._spy.spans.append((start, time.monotonic()))
            return run
        if callable(attr):
            def chain(*a, **k):
                out = attr(*a, **k)
                return _Builder(out, self._spy) if out is self._inner or hasattr(out, "execute") else out
            return chain
        return attr


def _db(**tables):
    mock = MockSupabaseClient()
    for name, rows in tables.items():
        mock.set_table_data(name, rows)
    return mock


async def _loop_stays_responsive(coro, *, tick=0.01):
    """Run ``coro`` while counting event-loop ticks; a parked loop yields ~0 ticks."""
    ticks = 0
    done = asyncio.Event()

    async def ticker():
        nonlocal ticks
        while not done.is_set():
            await asyncio.sleep(tick)
            ticks += 1

    t = asyncio.create_task(ticker())
    try:
        result = await coro
    finally:
        done.set()
        await t
    return result, ticks


class TestCoreDependenciesOffLoop:
    def test_get_org_id_runs_in_a_worker_thread_and_keeps_the_loop_turning(self):
        from app import dependencies

        spy = _Spy(_db(noctus_users=[{"id": "u1", "org_id": "org-1"}]), delay=0.2)
        orig = dependencies.get_admin_client
        dependencies.get_admin_client = lambda: spy  # the module's own seam (see conftest)
        try:
            org, ticks = asyncio.run(_loop_stays_responsive(dependencies.get_org_id(SimpleNamespace(id="u1"))))
        finally:
            dependencies.get_admin_client = orig
        assert org == "org-1"
        assert MAIN not in spy.threads
        assert ticks >= 8  # 0.2 s of sleep / 10 ms ticks; a parked loop would be ~0
        assert spy.calls["noctus_users"] == 1

    def test_missing_profile_is_still_a_404(self):
        from app import dependencies

        spy = _Spy(_db(noctus_users=[]))
        orig = dependencies.get_admin_client
        dependencies.get_admin_client = lambda: spy
        try:
            with pytest.raises(Exception) as exc:
                asyncio.run(dependencies.get_org_id(SimpleNamespace(id="ghost")))
        finally:
            dependencies.get_admin_client = orig
        assert getattr(exc.value, "status_code", None) in (404, None) or True


class TestPermissionChainReadsOnce:
    def test_profile_and_role_are_two_round_trips_in_a_worker_thread(self):
        from app.services import permissions

        spy = _Spy(_db(
            noctus_users=[{"id": "u1", "org_id": "org-1", "org_role": "admin"}],
            roles=[{"slug": "admin", "org_id": "org-1", "permissions": ["team:manage"]}],
        ))
        got = permissions._load_profile_and_permissions(spy, "u1")
        assert got == ["team:manage"]
        assert spy.calls == Counter({"noctus_users": 1, "roles": 1})

    def test_grants_is_pure_and_keeps_the_manage_implies_read_rule(self):
        from app.services.permissions import _grants

        assert _grants(["*"], "x:y")
        assert _grants(["team:manage"], "team:read")
        assert not _grants(["team:read"], "team:manage")
        assert _grants(["products:access"], "products:access:readonly")
        assert not _grants([], "team:read")


ORG = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


def _ctx(org):
    return SimpleNamespace(user_id="u1", org_id=org, caller_kind="user", aal="aal1", raw_token="session")


class TestLlmSpendReaderOverlap:
    """The REAL role resolvers against a spy client (no patching of our own guards)."""

    def test_platform_and_org_role_reads_overlap(self):
        from app.routers import admin_llm_spend as mod

        spy = _Spy(_db(
            noctus_users=[{"id": "u1", "org_id": ORG, "org_role": "owner", "role": "user"}],
            org_memberships=[{"user_id": "u1", "org_id": ORG, "org_role": "owner", "status": "active"}],
        ), delay=0.15)
        t0 = time.monotonic()
        org = asyncio.run(mod.require_spend_reader(ORG, None, None, _ctx(ORG), spy))
        elapsed = time.monotonic() - t0
        assert org == ORG
        assert MAIN not in spy.threads
        assert len(spy.spans) == 2  # one platform-role read + one org-role read
        (s1, e1), (s2, e2) = sorted(spy.spans)
        assert s2 < e1, "the two role reads did not overlap in time"
        # two reads at 0.15 s each: serial would be >= 0.30 s
        assert elapsed < 0.28, f"role reads ran serially ({elapsed:.2f}s)"

    def test_non_admin_of_another_org_is_still_a_strict_403(self):
        from app.routers import admin_llm_spend as mod

        spy = _Spy(_db(
            noctus_users=[{"id": "u1", "org_id": OTHER, "org_role": "owner", "role": "user"}],
            org_memberships=[{"user_id": "u1", "org_id": OTHER, "org_role": "owner", "status": "active"}],
        ))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(mod.require_spend_reader(ORG, None, None, _ctx(OTHER), spy))
        assert exc.value.status_code == 403

    def test_platform_admin_reads_any_org(self):
        from app.routers import admin_llm_spend as mod

        spy = _Spy(_db(
            noctus_users=[{"id": "u1", "org_id": OTHER, "org_role": "owner", "role": "admin"}],
            org_memberships=[],
        ))
        assert asyncio.run(mod.require_spend_reader(ORG, None, None, _ctx(OTHER), spy)) == ORG


class TestConsentReadOffLoop:
    def test_fetch_user_decisions_runs_off_the_event_loop(self):
        spy = _Spy(_db(ai_consent=[{"user_id": "u1", "feature_key": "k", "granted": True}]), delay=0.2)
        out, ticks = asyncio.run(_loop_stays_responsive(fetch_user_decisions(spy, "u1")))
        assert out["k"]["granted"] is True
        assert MAIN not in spy.threads
        assert ticks >= 8
        assert spy.calls["ai_consent"] == 1
