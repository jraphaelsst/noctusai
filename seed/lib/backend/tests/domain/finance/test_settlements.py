"""Settlements, ledger rows, reversal, idempotency, transfers."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.finance import accounts, entries, settlements
from noctusai_lib.domain.finance.errors import FinanceError

from .conftest import mk_account, mk_entry


def ledger(s, acc=None):
    rows = s.rows("ledger", eq={"account_id": str(acc["id"])} if acc else None)
    return sorted(rows, key=lambda r: (r.get("created_at", ""), r["id"]))


def pay(s, entry, acc, amount, **over):
    return settlements.settle_entry(s, entry["id"], {"account_id": acc["id"], "amount_cents": amount, **over})


def entry_now(s, entry):
    return s.find("entries", entry["id"])


# ── status recompute ──


def test_partial_then_paid_recomputes_status(s):
    e, acc = mk_entry(s, amount_cents=10000), mk_account(s)
    out = pay(s, e, acc, 4000)
    assert (out["entry"]["settled_cents"], out["entry"]["status"]) == (4000, "partial")
    out = pay(s, e, acc, 6000)
    assert (out["entry"]["settled_cents"], out["entry"]["status"]) == (10000, "paid")
    assert entry_now(s, e)["status"] == "paid"


def test_cannot_pay_more_than_the_open_balance(s):
    e, acc = mk_entry(s, amount_cents=1000), mk_account(s)
    pay(s, e, acc, 900)
    with pytest.raises(FinanceError) as err:
        pay(s, e, acc, 200)
    assert (err.value.status_code, err.value.code) == (422, "baixa_excede_saldo")
    assert entry_now(s, e)["settled_cents"] == 900


def test_refund_reduces_settled_and_cannot_exceed_it(s):
    e, acc = mk_entry(s, amount_cents=1000), mk_account(s)
    pay(s, e, acc, 1000)
    out = pay(s, e, acc, 300, kind="refund")
    assert (out["entry"]["settled_cents"], out["entry"]["status"]) == (700, "partial")
    with pytest.raises(FinanceError) as err:
        pay(s, e, acc, 800, kind="refund")
    assert err.value.code == "estorno_excede_pago"


def test_cancelled_entry_takes_no_settlement(s):
    e, acc = mk_entry(s), mk_account(s)
    entries.cancel_entry(s, e["id"])
    with pytest.raises(FinanceError) as err:
        pay(s, e, acc, 100)
    assert (err.value.status_code, err.value.code) == (409, "lancamento_cancelado")


def test_settlement_needs_an_owned_active_account(s, s_b):
    e = mk_entry(s)
    foreign = mk_account(s_b)
    with pytest.raises(FinanceError) as err:
        pay(s, e, foreign, 100)
    assert err.value.status_code == 422 and err.value.details["field"] == "account_id"
    inactive = mk_account(s)
    accounts.update_account(s, inactive["id"], {"active": False})
    with pytest.raises(FinanceError) as err:
        pay(s, e, inactive, 100)
    assert err.value.code == "conta_inativa"
    assert s.rows("settlements") == [] and s.rows("ledger") == []


# ── ledger ──


@pytest.mark.parametrize("direction, kind, expected", [
    ("receivable", "payment", "in"),
    ("receivable", "refund", "out"),
    ("payable", "payment", "out"),
    ("payable", "refund", "in"),
])
def test_ledger_direction_matrix(direction, kind, expected):
    assert settlements.main_ledger_direction(direction, kind) == expected


def test_receivable_payment_books_amount_in_and_fee_out(s):
    e, acc = mk_entry(s, amount_cents=10000), mk_account(s)
    out = pay(s, e, acc, 10000, fee_cents=350, settled_on="2026-10-10")
    rows = {r["origin"]: r for r in ledger(s, acc)}
    assert (rows["settlement"]["direction"], rows["settlement"]["amount_cents"], rows["settlement"]["occurred_on"]) == ("in", 10000, "2026-10-10")
    assert (rows["fee"]["direction"], rows["fee"]["amount_cents"]) == ("out", 350)
    assert {r["settlement_id"] for r in rows.values()} == {out["settlement"]["id"]}
    assert accounts.account_balance(s, acc["id"])["balance_cents"] == 10000 - 350


def test_payable_payment_books_out(s):
    e, acc = mk_entry(s, direction="payable", amount_cents=5000), mk_account(s, opening_balance_cents=20000)
    pay(s, e, acc, 5000)
    assert accounts.account_balance(s, acc["id"])["balance_cents"] == 15000


def test_no_fee_row_when_fee_is_zero(s):
    e, acc = mk_entry(s), mk_account(s)
    pay(s, e, acc, 1000)
    assert [r["origin"] for r in ledger(s)] == ["settlement"]


# ── idempotency (external_ref) ──


def test_external_ref_makes_a_settlement_idempotent(s):
    e, acc = mk_entry(s, amount_cents=10000), mk_account(s)
    first = pay(s, e, acc, 10000, external_ref="pay_1", fee_cents=100)
    again = pay(s, e, acc, 10000, external_ref="pay_1", fee_cents=100)
    assert first["replayed"] is False and again["replayed"] is True
    assert again["settlement"]["id"] == first["settlement"]["id"]
    assert len(s.rows("settlements")) == 1 and len(ledger(s)) == 2
    assert entry_now(s, e)["settled_cents"] == 10000  # not doubled


def test_replay_heals_a_settlement_whose_ledger_rows_never_landed(s):
    e, acc = mk_entry(s, amount_cents=1000), mk_account(s)
    first = pay(s, e, acc, 1000, external_ref="pay_h", fee_cents=10)
    for r in ledger(s):  # simulate a crash between the settlement insert and the ledger insert
        s.tbl("ledger").delete().eq("id", r["id"]).execute()
    s.tbl("entries").update({"settled_cents": 0, "status": "open"}).eq("id", e["id"]).execute()
    again = pay(s, e, acc, 1000, external_ref="pay_h", fee_cents=10)
    assert again["settlement"]["id"] == first["settlement"]["id"]
    assert sorted(r["origin"] for r in ledger(s)) == ["fee", "settlement"]
    assert entry_now(s, e)["status"] == "paid"


def test_same_external_ref_on_another_entry_is_refused(s):
    a, b, acc = mk_entry(s), mk_entry(s, description="outro"), mk_account(s)
    pay(s, a, acc, 100, external_ref="pay_x")
    with pytest.raises(FinanceError) as err:
        pay(s, b, acc, 100, external_ref="pay_x")
    assert (err.value.status_code, err.value.code) == (409, "baixa_duplicada")


def test_external_ref_is_per_kind(s):
    e, acc = mk_entry(s, amount_cents=1000), mk_account(s)
    pay(s, e, acc, 1000, external_ref="x1")
    out = pay(s, e, acc, 100, external_ref="x1", kind="refund")  # same ref, other kind: distinct settlement
    assert out["replayed"] is False and len(s.rows("settlements")) == 2


def test_external_ref_is_per_org(s, s_b):
    ea, eb = mk_entry(s), mk_entry(s_b)
    pay(s, ea, mk_account(s), 100, external_ref="shared")
    out = settlements.settle_entry(s_b, eb["id"], {"account_id": mk_account(s_b)["id"], "amount_cents": 100, "external_ref": "shared"})
    assert out["replayed"] is False


# ── reversal ──


def test_reversal_books_opposite_rows_and_never_deletes(s):
    e, acc = mk_entry(s, amount_cents=10000), mk_account(s)
    st = pay(s, e, acc, 10000, fee_cents=200)["settlement"]
    out = settlements.reverse_settlement(s, st["id"], "pagamento duplicado", user_id="u-1")
    assert out["entry"]["status"] == "open" and out["entry"]["settled_cents"] == 0
    assert out["settlement"]["reversal_reason"] == "pagamento duplicado" and out["settlement"]["reversed_by"] == "u-1"
    rows = ledger(s)
    assert len(rows) == 4  # originals kept + two opposite rows
    reversals = [r for r in rows if r.get("reverses_id")]
    assert {(r["origin"], r["direction"], r["amount_cents"]) for r in reversals} == {("settlement", "out", 10000), ("fee", "in", 200)}
    assert accounts.account_balance(s, acc["id"])["balance_cents"] == 0
    assert s.find("settlements", st["id"])["reversed_at"]  # the row is still there


def test_reverse_twice_is_409(s):
    e, acc = mk_entry(s), mk_account(s)
    st = pay(s, e, acc, 1000)["settlement"]
    settlements.reverse_settlement(s, st["id"], "motivo")
    with pytest.raises(FinanceError) as err:
        settlements.reverse_settlement(s, st["id"], "motivo")
    assert (err.value.status_code, err.value.code) == (409, "baixa_ja_estornada")
    assert len([r for r in ledger(s) if r.get("reverses_id")]) == 1


def test_reversal_requires_a_reason(s):
    e, acc = mk_entry(s), mk_account(s)
    st = pay(s, e, acc, 1000)["settlement"]
    with pytest.raises(FinanceError):
        settlements.reverse_settlement(s, st["id"], "   ")


def test_reversed_payment_frees_the_balance_for_a_new_one(s):
    e, acc = mk_entry(s, amount_cents=1000), mk_account(s)
    st = pay(s, e, acc, 1000, external_ref="p1")["settlement"]
    settlements.reverse_settlement(s, st["id"], "x")
    out = pay(s, e, acc, 1000)
    assert out["entry"]["status"] == "paid"


def test_cannot_reverse_a_payment_that_a_refund_depends_on(s):
    e, acc = mk_entry(s, amount_cents=1000), mk_account(s)
    st = pay(s, e, acc, 1000)["settlement"]
    refund = pay(s, e, acc, 400, kind="refund")["settlement"]
    with pytest.raises(FinanceError) as err:
        settlements.reverse_settlement(s, st["id"], "x")
    assert (err.value.status_code, err.value.code) == (409, "baixa_com_estorno")
    out = settlements.reverse_settlement(s, refund["id"], "refund wrong")
    assert out["entry"]["settled_cents"] == 1000 and out["entry"]["status"] == "paid"


def test_reversal_converges_after_a_half_done_attempt(s):
    e, acc = mk_entry(s), mk_account(s)
    st = pay(s, e, acc, 1000)["settlement"]
    original = ledger(s)[0]
    # A crash after the opposite ledger row landed but before `reversed_at` was stamped:
    s.tbl("ledger").insert({
        "id": "11111111-1111-1111-1111-111111111111", "org_id": s.org_id, "account_id": acc["id"],
        "occurred_on": "2026-10-13", "direction": "out", "amount_cents": 1000, "origin": "settlement",
        "settlement_id": st["id"], "reverses_id": original["id"],
    }).execute()
    settlements.reverse_settlement(s, st["id"], "retry")
    assert len([r for r in ledger(s) if r.get("reverses_id")]) == 1  # not booked twice
    assert s.find("settlements", st["id"])["reversed_at"]


def test_settlement_of_another_org_is_a_404(s, s_b):
    from noctusai_lib.primitives.exceptions import NotFoundError

    other = pay(s_b, mk_entry(s_b), mk_account(s_b), 100)["settlement"]
    with pytest.raises(NotFoundError):
        settlements.reverse_settlement(s, other["id"], "x")
    with pytest.raises(NotFoundError):
        pay(s, mk_entry(s_b), mk_account(s), 100)  # entry belongs to B


# ── transfers ──


def test_transfer_is_two_ledger_rows_sharing_a_group_and_never_an_entry(s):
    a, b = mk_account(s, "A"), mk_account(s, "B")
    out = settlements.create_transfer(s, {"from_account_id": a["id"], "to_account_id": b["id"], "amount_cents": 500, "occurred_on": "2026-10-10"})
    rows = ledger(s)
    assert len(rows) == 2 and {r.get("transfer_group") for r in rows} == {out["transfer_group"]}
    assert {(r["account_id"], r["direction"], r["origin"]) for r in rows} == {(a["id"], "out", "transfer"), (b["id"], "in", "transfer")}
    assert s.rows("entries") == [] and s.rows("settlements") == []


def test_transfer_rules(s, s_b):
    a, b = mk_account(s), mk_account(s)
    with pytest.raises(FinanceError):
        settlements.create_transfer(s, {"from_account_id": a["id"], "to_account_id": a["id"], "amount_cents": 1})
    with pytest.raises(FinanceError):
        settlements.create_transfer(s, {"from_account_id": a["id"], "to_account_id": b["id"], "amount_cents": 0})
    foreign = mk_account(s_b)
    with pytest.raises(FinanceError) as err:
        settlements.create_transfer(s, {"from_account_id": a["id"], "to_account_id": foreign["id"], "amount_cents": 1})
    assert err.value.details["field"] == "to_account_id"
    assert ledger(s) == []
