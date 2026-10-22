"""Read-path latency mechanism: independent reads overlap, handlers never park the event loop.

Numbers are pinned first (the report totals must not move); the mechanism is pinned second
(round-trip count, wall-clock overlap, handler kind). The delay proxy only wraps the DB
the Scope is handed -- no seed code is patched.
"""
from __future__ import annotations

import inspect
import threading
import time
from datetime import date

from noctusai_lib.domain.finance import accounts, reports
from noctusai_lib.domain.finance._common import Scope, run_parallel

from .conftest import CFG, ORG_A, build_harness, mk_account, mk_entry
from .test_reports import pay

DELAY = 0.15


class DelayDb:
    """Counts `.table()` round trips and makes each one cost DELAY seconds (a network hop)."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = 0
        self.threads: set[int] = set()
        self._lock = threading.Lock()

    def table(self, name):
        with self._lock:
            self.calls += 1
            self.threads.add(threading.get_ident())
        time.sleep(DELAY)
        return self._inner.table(name)

    def __getattr__(self, item):
        return getattr(self._inner, item)


def _seed(s):
    acc = mk_account(s, opening_balance_cents=1000, opening_date="2026-01-01")
    r1 = mk_entry(s, direction="receivable", due_date="2026-02-10", amount_cents=5000)
    mk_entry(s, direction="payable", due_date="2026-02-12", amount_cents=2000)
    pay(s, r1, acc, 3000, "2026-02-11", fee_cents=100)
    return acc


def test_cashflow_totals_are_pinned_and_reads_overlap(s, db):
    acc = _seed(s)
    baseline = reports.cashflow(s, date(2026, 2, 1), date(2026, 3, 31))
    baseline_acc = reports.cashflow(s, date(2026, 2, 1), date(2026, 3, 31), account_id=acc["id"])
    assert baseline["opening_balance_cents"] == 1000
    assert baseline["totals"] == {
        "realized_in_cents": 3000, "realized_out_cents": 100, "projected_in_cents": 2000, "projected_out_cents": 2000,
    }

    slow = DelayDb(db)
    ss = Scope(slow, CFG, ORG_A)
    t0 = time.perf_counter()
    got = reports.cashflow(ss, date(2026, 2, 1), date(2026, 3, 31))
    wall = time.perf_counter() - t0
    assert got == baseline  # identical numbers
    assert slow.calls == 4  # accounts + ledger<from + ledger in range + open entries
    assert wall < DELAY * 2.5  # sequential would be >= 4 * DELAY
    assert len(slow.threads) > 1

    slow_acc = DelayDb(db)
    got_acc = reports.cashflow(Scope(slow_acc, CFG, ORG_A), date(2026, 2, 1), date(2026, 3, 31), account_id=acc["id"])
    assert got_acc == baseline_acc
    assert slow_acc.calls == 5  # + the ownership check, overlapped with the rest


def test_account_balance_overlaps_lookup_and_ledger(s, db):
    acc = _seed(s)
    want = accounts.account_balance(s, acc["id"], date(2026, 12, 31))
    slow = DelayDb(db)
    t0 = time.perf_counter()
    got = accounts.account_balance(Scope(slow, CFG, ORG_A), acc["id"], date(2026, 12, 31))
    assert time.perf_counter() - t0 < DELAY * 1.8
    assert got == want and slow.calls == 2


def test_run_parallel_orders_results_and_raises_first_failure():
    assert run_parallel(lambda: 1, lambda: 2, lambda: 3) == [1, 2, 3]

    def boom(tag):
        def f():
            raise ValueError(tag)
        return f

    try:
        run_parallel(lambda: 0, boom("first"), boom("second"))
    except ValueError as exc:
        assert str(exc) == "first"
    else:
        raise AssertionError("expected a failure")


def test_awaitless_handlers_are_plain_def():
    """A coroutine handler running sync DB calls parks the event loop (the 3x765 ms staircase)."""
    h = build_harness()
    for route in h.app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None or "/finance" not in route.path:
            continue
        if inspect.iscoroutinefunction(endpoint):
            src = inspect.getsource(endpoint)
            assert "await " in src, f"{route.path}: async handler without await blocks the loop"
