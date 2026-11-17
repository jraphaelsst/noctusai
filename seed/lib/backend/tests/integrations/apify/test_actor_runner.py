import json
from decimal import Decimal

import httpx
import pytest

from noctusai_lib.integrations.apify import (
    ApifyActorTimeout, ApifyNotConfigured, ApifyRateLimited, ApifyRunFailed,
    FakeActorRunner, RealActorRunner, make_actor_runner,
)

TOKEN = "apify_api_SECRET123"


def _runner(handler, **kw):
    return RealActorRunner(token=TOKEN, transport=httpx.MockTransport(handler), **kw)


def _happy(seen=None, status="SUCCEEDED", items=None):
    items = [{"a": 1}, {"a": 2}, "junk"] if items is None else items

    def handler(req: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(req)
        assert req.headers["authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in str(req.url)
        p = req.url.path
        if req.method == "POST" and p.endswith("/runs"):
            return httpx.Response(201, json={"data": {"id": "RUN1", "status": "RUNNING"}})
        if p.endswith("/actor-runs/RUN1"):
            return httpx.Response(200, json={"data": {
                "id": "RUN1", "status": status, "defaultDatasetId": "DS1",
                "usageTotalUsd": 0.0123, "usage": {"ACTOR_COMPUTE_UNITS": 0.05}}})
        if p.endswith("/datasets/DS1/items"):
            return httpx.Response(200, json=items)
        return httpx.Response(404)
    return handler


def test_run_actor_returns_items_and_usage():
    seen = []
    res = _runner(_happy(seen)).run_actor("apify/web-scraper", {"q": "x"}, max_items=5)
    assert res.items == [{"a": 1}, {"a": 2}]  # non-object dropped, never silently renamed
    assert res.usage.run_id == "RUN1" and res.usage.results == 2
    assert res.usage.compute_units == Decimal("0.05") and res.usage.usd == Decimal("0.0123")
    start = seen[0]
    assert start.url.path.endswith("/acts/apify~web-scraper/runs")
    assert json.loads(start.content) == {"q": "x"}
    assert start.url.params["maxItems"] == "5"
    assert seen[-1].url.params["limit"] == "5"


def test_failed_run_is_typed_error():
    with pytest.raises(ApifyRunFailed, match="FAILED"):
        _runner(_happy(status="FAILED")).run_actor("a/b")


def test_non_list_dataset_is_typed_error():
    with pytest.raises(ApifyRunFailed, match="dataset shape"):
        _runner(_happy(items={"oops": 1})).run_actor("a/b")


def test_429_retry_after_then_success():
    calls = {"n": 0}
    inner = _happy()

    def handler(req):
        if req.method == "POST" and req.url.path.endswith("/runs"):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, headers={"retry-after": "2"})
        return inner(req)
    assert len(_runner(handler).run_actor("a/b").items) == 2
    assert calls["n"] == 2


def test_429_beyond_inline_max_is_retry_later_not_retried():
    from noctusai_lib.integrations.rate_limit import RetryLater
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, headers={"retry-after": "9999"})
    with pytest.raises(RetryLater):
        _runner(handler).run_actor("a/b")
    assert calls["n"] == 1


def test_timeout_aborts_and_raises():
    t = {"now": 0.0}
    seen = []

    def handler(req):
        seen.append(req)
        if req.method == "POST" and req.url.path.endswith("/runs"):
            return httpx.Response(201, json={"data": {"id": "RUN1", "status": "RUNNING"}})
        if req.url.path.endswith("/abort"):
            return httpx.Response(200, json={"data": {}})
        t["now"] += 100  # each poll "takes" 100s
        return httpx.Response(200, json={"data": {"id": "RUN1", "status": "RUNNING"}})
    r = _runner(handler, monotonic=lambda: t["now"], sleep=lambda s: None)
    with pytest.raises(ApifyActorTimeout):
        r.run_actor("a/b", timeout_s=150)
    assert any(q.url.path.endswith("/abort") for q in seen)


def test_token_never_in_error():
    def handler(req):
        return httpx.Response(500, text=f"boom {TOKEN}")
    with pytest.raises(ApifyRunFailed) as e:
        _runner(handler).run_actor("a/b")
    assert TOKEN not in str(e.value)


def test_bad_actor_id_rejected():
    with pytest.raises(ValueError):
        _runner(_happy()).run_actor("a/b/c")
    with pytest.raises(ValueError):
        FakeActorRunner({}).run_actor("")


def test_fake_parity_shape_and_usage():
    f = FakeActorRunner({"a/b": [{"x": 1}, {"x": 2}, {"x": 3}]})
    res = f.run_actor("a/b", {"k": 1}, max_items=2)
    assert res.items == [{"x": 1}, {"x": 2}] and res.usage.results == 2
    assert res.usage.compute_units is not None and f.calls[0]["input"] == {"k": 1}
    with pytest.raises(ApifyRunFailed):
        f.run_actor("unknown/actor")
    err = FakeActorRunner({}, raises=ApifyRateLimited())
    with pytest.raises(ApifyRateLimited):
        err.run_actor("a/b")


def test_factory_fake_or_refuse():
    with pytest.raises(ApifyNotConfigured):
        make_actor_runner(token=None)
    assert isinstance(make_actor_runner(token=None, allow_fake=True), FakeActorRunner)
    assert isinstance(make_actor_runner(token=None, real=False), FakeActorRunner)
    assert isinstance(make_actor_runner(token=TOKEN), RealActorRunner)
