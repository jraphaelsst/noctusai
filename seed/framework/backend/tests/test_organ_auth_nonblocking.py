"""`make_organ_auth` never parks the event loop, and one request resolves the effective org ONCE.

Live evidence (orbity prod, 2026-10-22): four concurrent finance GETs came back as a 401/420/458/569 ms
staircase because the organ auth wrapper ran sync PostgREST round trips on the loop -- and re-resolved the
org the base auth dep had just resolved. Real resolver, real dependency wiring, a fake core client whose
every call sleeps (no monkeypatching of our own code).

KB § PATTERNS/backend/request-path-latency.md
"""
from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import httpx
from fastapi import Depends, FastAPI, Header

from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.effective_org import acting_header_of, resolve_effective_org_for_request
from noctusai_lib.api.request_memo import RequestMemoMiddleware
from noctusai_lib.testing import MockSupabaseClient
from noctusai_seed.organ_auth import make_organ_auth

HOME = "org-home"
SLEEP = 0.2


class CountingCore:
    """Wraps a core client: every `.table()` is one counted, SLOW (sync) round trip."""

    def __init__(self, users, sleep=SLEEP):
        self._inner = MockSupabaseClient()
        self._inner.set_table_data("noctus_users", users)
        self._sleep = sleep
        self.calls = 0
        self._lock = threading.Lock()

    def table(self, name):
        with self._lock:
            self.calls += 1
        time.sleep(self._sleep)
        return self._inner.table(name)


def _users(*ids):
    return [{"id": i, "org_id": HOME, "org_role": "owner", "role": "user"} for i in ids]


def _app(core, *, base_resolves: bool):
    async def base(authorization: str | None = Header(None)):
        uid = (authorization or "").removeprefix("Bearer ")
        if base_resolves:
            # what the license gate / base auth dep does for the same request
            await run_blocking(resolve_effective_org_for_request, core, uid, token=uid)
        return (SimpleNamespace(id=uid), uid, HOME)

    deps = make_organ_auth(base, lambda: core)
    app = FastAPI()
    app.add_middleware(RequestMemoMiddleware)

    @app.get("/who")
    async def who(a=Depends(deps.auth)):
        return {"admin": a.is_admin}

    return app


async def _get_many(app, tokens):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        t0 = time.perf_counter()
        rs = await asyncio.gather(*[c.get("/who", headers={"Authorization": f"Bearer {t}"}) for t in tokens])
        return rs, time.perf_counter() - t0


def test_concurrent_organ_auth_requests_overlap_instead_of_serializing():
    n = 5
    tokens = [f"u{i}" for i in range(n)]
    core = CountingCore(_users(*tokens))
    rs, elapsed = asyncio.run(_get_many(_app(core, base_resolves=False), tokens))
    assert [r.json() for r in rs] == [{"admin": True}] * n
    # Serialized on the loop this is n * SLEEP = 1.0 s; in worker threads it is ~SLEEP.
    assert elapsed < n * SLEEP * 0.6, elapsed


def test_one_request_through_base_and_organ_auth_resolves_the_org_once():
    core = CountingCore(_users("u1"), sleep=0)
    rs, _ = asyncio.run(_get_many(_app(core, base_resolves=True), ["u1"]))
    assert rs[0].json() == {"admin": True}
    assert core.calls == 1  # was 2 (base + organ wrapper): one noctus_users read


def test_without_the_middleware_every_resolution_hits_the_database_as_before():
    core = CountingCore(_users("u1"), sleep=0)
    app = _app(core, base_resolves=True)
    app.user_middleware.clear()
    app.middleware_stack = None
    rs, _ = asyncio.run(_get_many(app, ["u1"]))
    assert rs[0].json() == {"admin": True}
    assert core.calls == 2  # no request scope => no memo => exactly today's behaviour


def test_memo_never_leaks_across_requests_users_or_tokens():
    core = CountingCore(_users("u1", "u2"), sleep=0)
    app = _app(core, base_resolves=True)
    # same user, two separate requests: re-resolved each time (1 per request)
    asyncio.run(_get_many(app, ["u1"]))
    asyncio.run(_get_many(app, ["u1"]))
    assert core.calls == 2
    # two different users concurrently: each resolved for itself
    core.calls = 0
    rs, _ = asyncio.run(_get_many(app, ["u1", "u2"]))
    assert [r.status_code for r in rs] == [200, 200]
    assert core.calls == 2


def test_memo_is_keyed_on_token_and_acting_header_within_one_request():
    from noctusai_lib.api.request_memo import memoize_for_request

    core = CountingCore(_users("u1"), sleep=0)

    async def run():
        # inside a request scope
        scope = {"type": "http"}

        async def app(scope, receive, send):
            for kw in ({"token": "a"}, {"token": "a"}, {"token": "b"}, {"token": "a", "acting_header": "x"}):
                resolve_effective_org_for_request(core, "u1", **kw)

        await RequestMemoMiddleware(app)(scope, None, None)

    asyncio.run(run())
    assert core.calls == 3  # (a) (b) (a,x) -- the repeated (a) was memoized
    assert memoize_for_request(("k",), lambda: 1) == 1  # outside a request: plain compute


def test_errors_are_not_memoized():
    from noctusai_lib.api.request_memo import memoize_for_request

    seen = []

    def boom():
        seen.append(1)
        raise RuntimeError("db down")

    async def run():
        async def app(scope, receive, send):
            for _ in range(2):
                try:
                    memoize_for_request(("e",), boom)
                except RuntimeError:
                    pass

        await RequestMemoMiddleware(app)({"type": "http"}, None, None)

    asyncio.run(run())
    assert len(seen) == 2
