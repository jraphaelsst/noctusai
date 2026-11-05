"""`aggregate_ai_usage` per-agent / per-session / attribution grouping and the new reader filters."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noctusai_lib.integrations.llm.ledger_read import aggregate_ai_usage, read_ai_usage_rows
from noctusai_lib.testing.mocks import MockSupabaseClient


def _r(i, org, product, agent, conv, cost, at="2026-10-20T12:00:00+00:00"):
    return {
        "id": i, "created_at": at, "org_id": org, "product": product, "feature": "f", "provider": "p", "model": "m",
        "agent_key": agent, "conversation_id": conv, "input_tokens": 10, "output_tokens": 2,
        "cost_usd": cost, "cost_brl": cost * 5, "status": "ok",
    }


ROWS = [
    _r(1, "o1", "sw", "julia", "c1", 0.3, "2026-10-20T10:00:00+00:00"),
    _r(2, "o2", "sw", "julia", "c1", 0.2, "2026-10-20T11:00:00+00:00"),
    _r(3, "o1", "sw", None, None, 0.1),
    _r(4, "o1", "agents", "studio", "c9", 1.0),
]


def test_per_product_per_agent_sums_across_orgs_and_keeps_null():
    agg = aggregate_ai_usage(ROWS)
    sw = agg["per_product"]["sw"]
    assert sw["calls"] == 3 and sw["cost_usd"] == pytest.approx(0.6)
    agents = {a["agent_key"]: a for a in sw["per_agent"]}
    assert agents["julia"]["calls"] == 2 and agents["julia"]["conversations"] == 1
    assert agents["julia"]["cost_brl"] == pytest.approx(2.5)
    assert agents[None]["conversations"] == 0
    assert sw["per_agent"][0]["agent_key"] == "julia"  # cost desc


def test_attribution_and_sessions_top_by_cost():
    agg = aggregate_ai_usage(ROWS)
    assert agg["attribution"] == {"calls_with_agent": 3, "calls_without_agent": 1}
    assert agg["per_session"][0]["conversation_id"] == "c9"
    c1 = next(s for s in agg["per_session"] if s["conversation_id"] == "c1" and s["org_id"] == "o1")
    assert c1["first"] == c1["last"] == "2026-10-20T10:00:00+00:00"


def test_sessions_capped_at_200():
    rows = [_r(i, "o", "p", "a", f"c{i}", 0.001 * i) for i in range(1, 260)]
    agg = aggregate_ai_usage(rows)
    assert len(agg["per_session"]) == 200 and agg["per_session"][0]["conversation_id"] == "c259"


def test_empty_is_backward_compatible():
    agg = aggregate_ai_usage([])
    assert agg["per_org"] == [] and agg["per_product"] == {} and agg["per_session"] == []
    assert agg["attribution"] == {"calls_with_agent": 0, "calls_without_agent": 0}


def test_reader_filters_agent_none_and_conversation():
    db = MockSupabaseClient()
    db.set_table_data("ai_usage", [dict(r) for r in ROWS])
    s, e = datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 31, tzinfo=timezone.utc)
    assert [r["id"] for r in read_ai_usage_rows(db, start=s, end=e, agent_key="none")] == [3]
    assert [r["id"] for r in read_ai_usage_rows(db, start=s, end=e, agent_key="studio")] == [4]
    assert {r["id"] for r in read_ai_usage_rows(db, start=s, end=e, conversation_id="c1")} == {1, 2}
