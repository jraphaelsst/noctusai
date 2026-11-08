"""Real Anthropic Admin adapter against recorded (synthetic) fixtures shaped like the docs.

Transport is httpx.MockTransport — the HTTP boundary, not our code. The key must never leak.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.services.ai_usage.anthropic_client import (
    BETA_HEADER,
    FakeAnthropicClient,
    RealAnthropicClient,
    SourceError,
    SourceUnavailable,
    make_anthropic_client,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "anthropic"
KEY = "sk-ant-admin-SYNTHETIC-DO-NOT-LEAK"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text())


def _client(handler, sleeps=None) -> RealAnthropicClient:
    return RealAnthropicClient(
        KEY, transport=httpx.MockTransport(handler), sleep=(sleeps.append if sleeps is not None else (lambda s: None))
    )


def test_usage_paginates_sends_beta_header_and_parses():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=_load("usage_page2.json" if req.url.params.get("page") else "usage_page1.json"))

    pull = _client(handler).fetch_usage(date(2026, 11, 1), date(2026, 11, 8))
    assert len(seen) == 2 and seen[1].url.params["page"] == "page_synthetic_2"
    assert all(r.headers["anthropic-beta"] == BETA_HEADER and r.headers["x-api-key"] == KEY for r in seen)
    assert seen[0].url.params["ending_at"] == "2026-11-09T00:00:00Z"  # inclusive end day -> exclusive bound
    first, second = pull.rows
    assert (first.day, first.cache_write_5m, first.cache_write_1h, first.web_search_requests) == (date(2026, 11, 2), 200, 10, 2)
    assert second.api_key_id == "apikey_synthetic" and second.workspace_id is None
    assert pull.data_refreshed_at.isoformat() == "2026-11-08T10:05:00+00:00"


def test_cost_keeps_decimal_cents():
    pull = _client(lambda r: httpx.Response(200, json=_load("cost_page1.json"))).fetch_cost(date(2026, 11, 1), date(2026, 11, 8))
    row = pull.rows[0]
    assert row.amount_cents == Decimal("1250.500000") and row.list_amount_cents == Decimal("1500.000000")
    assert (row.cost_type, row.token_type) == ("tokens", "output_tokens")


def test_rate_limits_map_org_scope():
    limits = _client(lambda r: httpx.Response(200, json=_load("rate_limits.json"))).fetch_rate_limits()
    assert {(l.scope, l.workspace_id, l.model_group, l.metric, l.limit) for l in limits} == {
        ("org", None, "Claude Test 1.x", "requests_per_minute", 1000),
        ("org", None, "Claude Test 1.x", "output_tokens_per_minute", 80000),
    }


def test_no_key_is_unavailable_without_any_http_call():
    calls = []
    c = RealAnthropicClient("", transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json={})))
    with pytest.raises(SourceUnavailable) as e:
        c.fetch_usage(date(2026, 11, 1), date(2026, 11, 2))
    assert e.value.reason_code == "no_admin_key" and calls == []


def test_403_is_individual_org_unavailable():
    with pytest.raises(SourceUnavailable) as e:
        _client(lambda r: httpx.Response(403, json={"error": {"type": "permission_error"}})).fetch_usage(
            date(2026, 11, 1), date(2026, 11, 2))
    assert e.value.reason_code == "individual_org"


@pytest.mark.parametrize("status,reason", [(400, "http_4xx"), (401, "http_4xx"), (500, "http_5xx"), (503, "http_5xx")])
def test_http_errors_map_to_reason_codes(status, reason):
    with pytest.raises(SourceError) as e:
        _client(lambda r: httpx.Response(status, json={})).fetch_cost(date(2026, 11, 1), date(2026, 11, 2))
    assert e.value.reason_code == reason and e.value.http_status == status


@pytest.mark.parametrize("body", [
    {"nope": 1},
    {"data": [{"starting_at": "2026-11-02T00:00:00Z"}], "data_refreshed_at": "2026-11-08T10:00:00Z"},
])
def test_schema_drift(body):
    with pytest.raises(SourceError) as e:
        _client(lambda r: httpx.Response(200, json=body)).fetch_usage(date(2026, 11, 1), date(2026, 11, 2))
    assert e.value.reason_code == "schema_drift"


def test_429_backs_off_honouring_retry_after_then_succeeds():
    n = {"i": 0}
    sleeps: list[float] = []

    def handler(req):
        n["i"] += 1
        if n["i"] == 1:
            return httpx.Response(429, headers={"retry-after": "3"}, json={})
        return httpx.Response(200, json=_load("cost_page1.json"))

    _client(handler, sleeps).fetch_cost(date(2026, 11, 1), date(2026, 11, 2))
    assert n["i"] == 2 and len(sleeps) == 1 and 3 <= sleeps[0] <= 4


def test_repr_never_contains_the_key():
    assert KEY not in repr(RealAnthropicClient(KEY)) and "set" in repr(RealAnthropicClient(KEY))


def test_factory_prefers_explicit_fake_and_builds_real_from_key():
    fake = FakeAnthropicClient()
    assert make_anthropic_client(fake=fake) is fake
    assert isinstance(make_anthropic_client("k"), RealAnthropicClient)
