"""The receivable-lifecycle half of the `FinanceBooking` seam (read / update / cancel / settle by entry id) --
the Supabase implementation over the finance services and the Fake, held to the SAME behaviour."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.finance import FakeFinanceBooking, NoopFinanceBooking, make_finance_booking

from noctusai_lib.primitives.exceptions import AppException, NotFoundError

from .conftest import CFG, ORG_A, ORG_B, VALID_CPF, mk_account

RECV = dict(
    source="external", source_ref="clients:session:1", description="Sessão — Ana", counterparty_name="Ana",
    counterparty_doc=VALID_CPF, amount_cents=10000, competence_month=date(2026, 10, 1), due_date=date(2026, 10, 20),
    category_hint="Serviços",
)


@pytest.fixture(params=["supabase", "fake"])
def pair(request, db, s):
    """`(booking, account_id)` -- the fake keeps no accounts, any id is accepted there."""
    if request.param == "fake":
        return FakeFinanceBooking(), "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
    return make_finance_booking("supabase", db=db, cfg=CFG), mk_account(s, "Banco")["id"]


def _settle(booking, account, entry_id, amount, ref, org=ORG_A):
    return booking.settle_receivable(org, entry_id, account_id=account, amount_cents=amount, settled_on=date(2026, 10, 25),
                                     method="pix", external_ref=ref)


def test_receivables_reads_by_id_scoped_to_the_org(pair):
    booking, _ = pair
    a = booking.book_receivable(ORG_A, **RECV)
    b = booking.book_receivable(ORG_A, **{**RECV, "source_ref": "clients:session:2", "amount_cents": 500})
    got = {r["id"]: r for r in booking.receivables(ORG_A, [a, b, a])}
    assert set(got) == {a, b}
    assert got[a] == {"id": a, "description": "Sessão — Ana", "amount_cents": 10000, "settled_cents": 0,
                      "due_date": "2026-10-20", "status": "open"}
    assert booking.receivables(ORG_B, [a, b]) == [] and booking.receivables(ORG_A, []) == []


def test_update_moves_amount_and_dates(pair):
    booking, _ = pair
    a = booking.book_receivable(ORG_A, **RECV)
    booking.update_receivable(ORG_A, a, amount_cents=12000, description="Sessão — Ana — nova", due_date=date(2026, 11, 3),
                              competence_month=date(2026, 11, 1))
    (r,) = booking.receivables(ORG_A, [a])
    assert (r["amount_cents"], r["description"], r["due_date"]) == (12000, "Sessão — Ana — nova", "2026-11-03")
    with pytest.raises(NotFoundError):
        booking.update_receivable(ORG_B, a, amount_cents=1)


def test_settle_partial_then_full_and_idempotent_on_ref(pair):
    booking, account = pair
    a = booking.book_receivable(ORG_A, **RECV)
    first = _settle(booking, account, a, 4000, "clients:payment:p1:" + a)
    assert _settle(booking, account, a, 4000, "clients:payment:p1:" + a) == first
    (r,) = booking.receivables(ORG_A, [a])
    assert (r["settled_cents"], r["status"]) == (4000, "partial")
    _settle(booking, account, a, 6000, "clients:payment:p2:" + a)
    (r,) = booking.receivables(ORG_A, [a])
    assert (r["settled_cents"], r["status"]) == (10000, "paid")
    with pytest.raises(AppException):
        _settle(booking, account, a, 1, "clients:payment:p3:" + a)  # nothing left to settle
    with pytest.raises(NotFoundError):
        _settle(booking, account, a, 1, "x", org=ORG_B)


def test_settled_receivable_refuses_cancel_and_shrinking(pair):
    booking, account = pair
    a = booking.book_receivable(ORG_A, **RECV)
    _settle(booking, account, a, 4000, "r1")
    with pytest.raises(AppException) as e:
        booking.cancel_receivable(ORG_A, a)
    assert e.value.status_code == 409
    with pytest.raises(AppException):
        booking.update_receivable(ORG_A, a, amount_cents=3000)


def test_cancel_then_book_under_a_new_ref(pair):
    booking, _ = pair
    a = booking.book_receivable(ORG_A, **RECV)
    booking.cancel_receivable(ORG_A, a)
    (r,) = booking.receivables(ORG_A, [a])
    assert r["status"] == "cancelled"
    assert booking.book_receivable(ORG_A, **RECV) == a  # same ref finds the cancelled one -- callers re-key
    assert booking.book_receivable(ORG_A, **{**RECV, "source_ref": RECV["source_ref"] + ":1"}) != a
    with pytest.raises(NotFoundError):
        booking.cancel_receivable(ORG_B, a)


def test_noop_lifecycle():
    noop = NoopFinanceBooking()
    assert noop.receivables(ORG_A, ["x"]) == []
    for call in (lambda: noop.update_receivable(ORG_A, "x", amount_cents=1), lambda: noop.cancel_receivable(ORG_A, "x"),
                 lambda: noop.settle_receivable(ORG_A, "x", account_id="a", amount_cents=1, settled_on=date(2026, 1, 1),
                                                method=None, external_ref="r")):
        with pytest.raises(NotFoundError):
            call()

