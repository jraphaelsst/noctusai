"""Shared rolling-window spend ceiling: reserve / refuse / fail-closed / cross-mechanism counting."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from noctusai_lib.integrations.llm import (
    InMemorySpendCeiling, SpendCeilingExceeded, SpendCeilingUnverifiable, SupabaseSpendCeiling, make_spend_ceiling,
)

ORG = UUID(int=1)
OTHER = UUID(int=2)
KEY = "automacao-avaliacoes"


def _reserve(c, kind, ref, amount, org=ORG, ceiling=10.0):
    c.reserve(ceiling_key=KEY, kind=kind, org_id=org, ref=ref, amount_usd=amount, ceiling_usd=ceiling)


def test_under_the_ceiling_reserves():
    c = InMemorySpendCeiling()
    _reserve(c, "eval_run", "r1", 4.0)
    _reserve(c, "eval_run", "r2", 6.0)  # exactly at the ceiling is allowed


def test_a_reservation_crossing_the_ceiling_is_refused_with_its_code():
    c = InMemorySpendCeiling()
    _reserve(c, "eval_run", "r1", 6.0)
    with pytest.raises(SpendCeilingExceeded) as ei:
        _reserve(c, "eval_run", "r2", 4.01)
    assert ei.value.status_code == 429 and ei.value.code == "SPEND_CEILING_EXCEEDED"


def test_spend_of_one_mechanism_counts_against_another():
    c = InMemorySpendCeiling()
    _reserve(c, "eval_run", "r1", 6.0)
    with pytest.raises(SpendCeilingExceeded):
        _reserve(c, "mecanismo_run", "m1", 5.0)


def test_settled_actual_replaces_the_reserved_cap():
    c = InMemorySpendCeiling()
    _reserve(c, "eval_run", "r1", 9.0)
    c.settle(ceiling_key=KEY, kind="eval_run", ref="r1", actual_usd=1.0)
    _reserve(c, "mecanismo_run", "m1", 9.0)


def test_other_orgs_and_expired_rows_do_not_count():
    now = [datetime(2026, 11, 9, tzinfo=timezone.utc)]
    c = InMemorySpendCeiling(clock=lambda: now[0])
    _reserve(c, "eval_run", "r1", 10.0)
    _reserve(c, "eval_run", "r2", 10.0, org=OTHER)
    now[0] += timedelta(hours=24, minutes=1)
    _reserve(c, "eval_run", "r3", 10.0)


def test_a_retry_of_the_same_run_is_not_double_counted():
    c = InMemorySpendCeiling()
    _reserve(c, "eval_run", "r1", 8.0)
    _reserve(c, "eval_run", "r1", 8.0)


def test_a_failed_lookup_is_refused_fail_closed_in_the_fake():
    c = InMemorySpendCeiling()
    c.fail_with = RuntimeError("down")
    with pytest.raises(SpendCeilingUnverifiable) as ei:
        _reserve(c, "eval_run", "r1", 1.0)
    assert ei.value.status_code == 503 and ei.value.code == "SPEND_CEILING_UNVERIFIABLE"


class _Rpc:
    def __init__(self, data=None, exc=None):
        self.data, self.exc, self.calls = data, exc, []

    def rpc(self, name, params):
        self.calls.append((name, params))
        outer = self

        class _Q:
            def execute(self_inner):
                if outer.exc:
                    raise outer.exc

                class _R:
                    data = outer.data
                return _R()
        return _Q()


def _real_reserve(client):
    SupabaseSpendCeiling(lambda: client).reserve(
        ceiling_key=KEY, kind="eval_run", org_id=ORG, ref="r1", amount_usd=2.0, ceiling_usd=10.0)


def test_real_reserve_maps_the_rpc_answer():
    ok = _Rpc({"allowed": True, "spent_usd": 1.0})
    _real_reserve(ok)
    assert ok.calls[0][0] == "spend_reserve" and ok.calls[0][1]["p_ceiling_usd"] == 10.0
    with pytest.raises(SpendCeilingExceeded):
        _real_reserve(_Rpc({"allowed": False, "spent_usd": 9.5}))


def test_real_reserve_fails_closed_on_any_lookup_failure():
    for bad in (_Rpc(exc=RuntimeError("boom")), _Rpc(data=None)):
        with pytest.raises(SpendCeilingUnverifiable):
            _real_reserve(bad)


def test_real_settle_is_best_effort_and_factory_picks_by_client():
    SupabaseSpendCeiling(lambda: _Rpc(exc=RuntimeError("x"))).settle(
        ceiling_key=KEY, kind="eval_run", ref="r1", actual_usd=1.0)
    assert isinstance(make_spend_ceiling(None), InMemorySpendCeiling)
    assert isinstance(make_spend_ceiling(lambda: None), SupabaseSpendCeiling)
