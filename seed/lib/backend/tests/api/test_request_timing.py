"""RequestTimingMiddleware: Server-Timing header + one route-TEMPLATE log line
per request, wired into configure_app (so every product gets it)."""
from __future__ import annotations

import logging
import re
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.api.app_factory import configure_app
from noctusai_lib.api.request_timing import LOG_PREFIX, UNMATCHED_ROUTE


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/api/things/{thing_id}")
    def thing(thing_id: str) -> dict:
        return {"id": thing_id}

    settings = SimpleNamespace(cors_origins_list=[], sentry_dsn="", is_production=False, debug=True)
    configure_app(app, settings)
    return TestClient(app)


def _lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.name == "noctusai.request_timing" and r.getMessage().startswith(LOG_PREFIX)]


def test_server_timing_header_present(caplog):
    r = _client().get("/api/things/abc")
    h = r.headers["server-timing"]
    assert re.match(r"app;dur=\d+(\.\d+)?, inflight;desc=\"1\", inflight_peak;desc=\"1\"", h)
    assert "blk" not in h  # no blocking hop -> metric omitted, never 0


def test_logs_route_template_never_the_raw_path(caplog):
    with caplog.at_level(logging.INFO, logger="noctusai.request_timing"):
        _client().get("/api/things/secret-id-123@x.com")
    lines = _lines(caplog)
    assert len(lines) == 1
    assert "route=/api/things/{thing_id}" in lines[0]
    assert "secret-id-123" not in lines[0]
    assert re.search(r"method=GET route=\S+ status=200 dur_ms=\d+\.\d", lines[0])


def test_unmatched_path_logs_bounded_placeholder(caplog):
    with caplog.at_level(logging.INFO, logger="noctusai.request_timing"):
        r = _client().get("/api/attacker-controlled/../path")
    lines = _lines(caplog)
    assert r.status_code == 404
    assert len(lines) == 1 and f"route={UNMATCHED_ROUTE}" in lines[0] and "attacker" not in lines[0]


# --------------------------------------------------------------------------- concurrency metrics
import asyncio
import time

import anyio
import httpx

from noctusai_lib.api.auth import _blocking
from noctusai_lib.api.auth._blocking import run_blocking, run_parallel, set_blocking_limiter


def _timing(h: str) -> dict:
    out = {}
    for part in h.split(", "):
        name, *params = part.split(";")
        d = {}
        for p in params:
            k, v = p.split("=", 1)
            d[k] = v.strip('"')
        out[name] = d
    return out


def _async_app() -> FastAPI:
    app = FastAPI()

    @app.get("/slow")
    async def slow() -> dict:
        await asyncio.sleep(0.15)
        return {}

    @app.get("/blk")
    async def blk() -> dict:
        await run_blocking(time.sleep, 0.1)
        return {}

    @app.get("/par")
    async def par() -> dict:
        await run_blocking(lambda: run_parallel(lambda: time.sleep(0.02), lambda: time.sleep(0.02)))
        return {}

    settings = SimpleNamespace(cors_origins_list=[], sentry_dsn="", is_production=False, debug=True)
    configure_app(app, settings)
    return app


async def _get_all(app, paths):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await asyncio.gather(*(c.get(p) for p in paths))


def test_concurrent_requests_show_inflight_and_lag_sampler_runs(caplog):
    with caplog.at_level(logging.INFO, logger="noctusai.request_timing"):
        rs = asyncio.run(_get_all(_async_app(), ["/slow"] * 4))
    t = [_timing(r.headers["server-timing"]) for r in rs]
    assert max(int(x["inflight_peak"]["desc"]) for x in t) == 4
    assert all(int(x["inflight_peak"]["desc"]) >= int(x["inflight"]["desc"]) for x in t)
    assert all("lag" in x for x in t)  # 150 ms request spans several 50 ms ticks
    assert all(re.search(r"dur_ms=\d+\.\d inflight=\d+ inflight_peak=4", ln) for ln in _lines(caplog))


def test_inflight_returns_to_zero_and_no_leaked_ticker():
    from noctusai_lib.api import request_timing as rt
    asyncio.run(_get_all(_async_app(), ["/slow"] * 3))
    assert rt._INFLIGHT == 0 and not rt._ACTIVE_STATS
    assert all(lp.is_closed() for lp in list(rt._TICKING))  # a pending tick dies with its loop


def test_blocking_hop_is_counted_with_run_time():
    (r,) = asyncio.run(_get_all(_async_app(), ["/blk"]))
    t = _timing(r.headers["server-timing"])
    assert t["blk"]["desc"] == "1" and float(t["blk"]["dur"]) >= 90
    assert float(t["blkq"]["dur"]) < 50  # default limiter: idle, no queue


def test_blkq_positive_when_injected_limiter_is_saturated():
    set_blocking_limiter(anyio.CapacityLimiter(1))  # injected seam, not a patch of any guard
    try:
        rs = asyncio.run(_get_all(_async_app(), ["/blk"] * 3))
    finally:
        set_blocking_limiter(None)
    waits = sorted(float(_timing(r.headers["server-timing"])["blkq"]["dur"]) for r in rs)
    assert waits[-1] >= 150  # the last request queued behind two 100 ms hops
    assert _blocking._limiter is None


def test_run_parallel_thunks_are_counted():
    (r,) = asyncio.run(_get_all(_async_app(), ["/par"]))
    t = _timing(r.headers["server-timing"])
    assert t["parq"]["desc"] == "2" and "dur" in t["parq"]


def test_run_blocking_outside_request_is_plain():
    assert asyncio.run(run_blocking(lambda: 7)) == 7
