"""Snapshot job on the Fake adapter + in-memory store (same replace semantics as the RPC)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from noctusai_lib.testing import MockSupabaseClient

from app.services.ai_usage.anthropic_client import (
    CostRow, FakeAnthropicClient, RateLimitRow, SourceError, UsageRow,
)
from app.services.ai_usage.snapshot import (
    COVERAGE_START, InMemorySyncStore, SupabaseSyncStore, contiguous_coverage, dims_key, is_final, plan_windows, run_snapshot,
)

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 11, 8)


def _run(client, store, notify=None, today=TODAY):
    return run_snapshot(client, store, today=today, clock=lambda: NOW, notify=notify)


def test_replace_window_drops_revised_rows():
    store = InMemorySyncStore()
    a = UsageRow(day=date(2026, 11, 2), model="m-a", uncached_input=10, output_tokens=1, requests=1)
    b = UsageRow(day=date(2026, 11, 3), model="m-b", uncached_input=20, output_tokens=2, requests=1)
    client = FakeAnthropicClient(usage=[a, b], cost=[CostRow(day=date(2026, 11, 2), model="m-a", amount_cents=Decimal("5"))])
    _run(client, store)
    assert {k[1] for k in store.usage} == {dims_key("m-a", None, None, None, None), dims_key("m-b", None, None, None, None)}
    # the revision removes m-b and changes m-a: a bare upsert would have kept m-b
    client.usage = [UsageRow(day=date(2026, 11, 2), model="m-a", uncached_input=99, output_tokens=1, requests=1)]
    client.cost = []
    summary = _run(client, store)
    assert [r["model"] for r in store.usage.values()] == ["m-a"]
    assert next(iter(store.usage.values()))["uncached_input"] == 99
    assert store.cost == {}
    assert summary["rows_deleted"] >= 2


def test_unavailable_is_recorded_not_raised_and_notifies_once_on_change():
    store, sent = InMemorySyncStore(), []
    client = FakeAnthropicClient(unavailable="individual_org")
    out = _run(client, store, notify=lambda t, m, md: sent.append(md))
    assert out["status"] == "unavailable" and out["reason_code"] == "individual_org"
    assert store.runs[-1]["status"] == "unavailable" and store.runs[-1]["reason_code"] == "individual_org"
    _run(client, store, notify=lambda t, m, md: sent.append(md))  # same state: no second notification
    assert sent == [{"reason_code": "individual_org"}]
    _run(FakeAnthropicClient(unavailable="no_admin_key"), store, notify=lambda t, m, md: sent.append(md))
    assert len(sent) == 2


def test_failure_records_error_and_raises_so_the_run_ledger_sees_it():
    store = InMemorySyncStore()
    with pytest.raises(SourceError):
        _run(FakeAnthropicClient(error=SourceError("http_5xx", http_status=502)), store)
    assert store.runs[-1]["status"] == "error" and store.runs[-1]["http_status"] == 502
    assert store.usage == {} and store.cost == {}


def test_nothing_is_written_when_a_later_pull_fails():
    class Boom(FakeAnthropicClient):
        def fetch_cost(self, start, end):
            raise SourceError("http_5xx", http_status=500)

    store = InMemorySyncStore()
    with pytest.raises(SourceError):
        _run(Boom(usage=[UsageRow(day=date(2026, 11, 2), model="m")]), store)
    assert store.usage == {}  # usage was pulled but nothing committed before cost completed


def test_rate_limits_replaced():
    store = InMemorySyncStore()
    client = FakeAnthropicClient(rate_limits=[RateLimitRow("org", None, "g", "requests_per_minute", 5)])
    _run(client, store)
    assert store.rate_limits[0]["limit_value"] == 5 and store.rate_limits[0]["workspace_id_key"] == ""


def test_windows_backfill_in_31_day_chunks_resumes_and_revises_previous_month_early():
    w = plan_windows(TODAY, None)
    assert w[0] == (date(2026, 11, 1), TODAY)
    assert w[1][0] == COVERAGE_START and all((b - a).days + 1 <= 31 for a, b in w[1:])
    assert w[-1][1] == date(2026, 10, 31)
    resumed = plan_windows(TODAY, date(2026, 9, 30))
    assert resumed[1] == (date(2026, 10, 1), date(2026, 10, 31)) and len(resumed) == 2
    early = plan_windows(date(2026, 11, 5), date(2026, 10, 31))
    assert early == [(date(2026, 10, 1), date(2026, 11, 5))]


def test_contiguous_coverage_ignores_windows_after_a_gap():
    assert contiguous_coverage([(date(2026, 1, 1), date(2026, 1, 31)), (date(2026, 11, 1), date(2026, 11, 8))]) == date(2026, 1, 31)
    assert contiguous_coverage([(date(2026, 3, 1), date(2026, 3, 31))]) is None


def test_is_final_after_month_end_plus_seven_days():
    refreshed = datetime(2026, 11, 8, tzinfo=timezone.utc)
    assert is_final(date(2026, 10, 15), refreshed)       # Oct 31 + 7d = Nov 7 < Nov 8
    assert not is_final(date(2026, 11, 2), refreshed)


def test_supabase_store_replaces_through_one_rpc_per_table():
    db = MockSupabaseClient()
    db.set_rpc_data("ai_replace_anthropic_usage_window", {"deleted": 1, "written": 2})
    store = SupabaseSyncStore(db)
    assert store.replace_usage(date(2026, 11, 1), date(2026, 11, 8), [{"day": "2026-11-02"}]) == (1, 2)
    name, params = db.rpc_calls[-1]
    assert name == "ai_replace_anthropic_usage_window" and params["p_from"] == "2026-11-01" and params["p_to"] == "2026-11-08"
