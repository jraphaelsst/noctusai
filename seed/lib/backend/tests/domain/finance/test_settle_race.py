"""Closes NOC-REMEDIATE[finance-settle-overpay-race]: settle + reverse run in a row-locked RPC."""
from __future__ import annotations

import threading

import pytest

from noctusai_lib.domain.finance import settlements
from noctusai_lib.domain.finance.errors import FinanceError
from noctusai_lib.domain.finance.sql import REVERSE_RPC, SETTLE_RPC, rpc_name

from .conftest import CFG, mk_account, mk_entry


def test_two_concurrent_manual_settlements_cannot_overpay(s, db):
    e, acc = mk_entry(s, amount_cents=1000), mk_account(s)
    gate, results, errors = threading.Barrier(2), [], []

    def go():
        gate.wait()
        try:
            results.append(settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": 700}))
        except FinanceError as exc:
            errors.append(exc.code)

    threads = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(results) == 1 and errors == ["baixa_excede_saldo"]
    assert s.find("entries", e["id"])["settled_cents"] == 700


def test_the_balance_is_derived_from_settlement_rows_not_the_cached_total(s):
    e, acc = mk_entry(s, amount_cents=1000), mk_account(s)
    settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": 900})
    # a stale cached total must not let an overpay through
    s.tbl("entries").update({"settled_cents": 0, "status": "open"}).eq("id", e["id"]).execute()
    with pytest.raises(FinanceError) as err:
        settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": 200})
    assert err.value.code == "baixa_excede_saldo"


def test_settle_and_reverse_go_through_the_prefixed_rpcs(s, db):
    e, acc = mk_entry(s, amount_cents=1000), mk_account(s)
    out = settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": 500})
    settlements.reverse_settlement(s, out["settlement"]["id"], "engano")
    names = [n for n, _ in db.rpc_calls]
    assert names == [rpc_name(CFG, SETTLE_RPC), rpc_name(CFG, REVERSE_RPC)]


def test_two_concurrent_reversals_reverse_once(s):
    e, acc = mk_entry(s, amount_cents=1000), mk_account(s)
    st = settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": 500})["settlement"]
    gate, ok, errors = threading.Barrier(2), [], []

    def go():
        gate.wait()
        try:
            settlements.reverse_settlement(s, st["id"], "engano")
            ok.append(1)
        except FinanceError as exc:
            errors.append(exc.code)

    ts = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(ok) == 1 and errors == ["baixa_ja_estornada"]
    rows = s.rows("ledger", eq={"settlement_id": st["id"]})
    assert len([r for r in rows if r.get("reverses_id")]) == 1  # one opposite row per original, no more
