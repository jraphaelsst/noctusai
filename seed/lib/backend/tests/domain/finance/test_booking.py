"""The `FinanceBooking` seam: idempotent receivable + settlement booking, Noop, Fake, factory."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.finance import (
    FakeFinanceBooking,
    FinanceBooking,
    NoopFinanceBooking,
    SupabaseFinanceBooking,
    accounts,
    make_finance_booking,
)
from noctusai_lib.domain.finance.errors import FinanceError
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import CFG, ORG_A, ORG_B, VALID_CPF, mk_account

RECV = dict(
    source="commerce_order", source_ref="order-1", description="Pedido #1", counterparty_name="Ana",
    counterparty_doc=VALID_CPF, amount_cents=10000, competence_month=date(2026, 10, 17), due_date=date(2026, 10, 20),
    category_hint="Vendas",
)


@pytest.fixture
def booking(db):
    return make_finance_booking("supabase", db=db, cfg=CFG)


def test_factory_kinds_and_protocol_conformance(db):
    assert isinstance(make_finance_booking(), NoopFinanceBooking)
    assert isinstance(make_finance_booking("fake"), FakeFinanceBooking)
    real = make_finance_booking("supabase", db=db, cfg=CFG)
    assert isinstance(real, SupabaseFinanceBooking)
    for impl in (NoopFinanceBooking(), FakeFinanceBooking(), real):
        assert isinstance(impl, FinanceBooking)
    with pytest.raises(ValueError):
        make_finance_booking("supabase")
    with pytest.raises(ValueError):
        make_finance_booking("carrier-pigeon")


def test_book_receivable_creates_and_is_idempotent(booking, s):
    first = booking.book_receivable(ORG_A, **RECV)
    again = booking.book_receivable(ORG_A, **RECV)
    assert first == again and len(s.rows("entries")) == 1
    e = s.find("entries", first)
    assert (e["direction"], e["source"], e["source_ref"], e["status"]) == ("receivable", "commerce_order", "order-1", "open")
    assert e["competence_month"] == "2026-10-01" and e["due_date"] == "2026-10-20" and e["amount_cents"] == 10000
    assert e["category_id"] is not None  # "Vendas" hint resolved to the default income category


def test_unknown_category_hint_books_uncategorized(booking, s):
    entry_id = booking.book_receivable(ORG_A, **{**RECV, "category_hint": "Nao existe"})
    assert s.find("entries", entry_id)["category_id"] is None


def test_receivables_are_tenant_isolated(booking, s, s_b):
    a = booking.book_receivable(ORG_A, **RECV)
    b = booking.book_receivable(ORG_B, **RECV)  # same source+ref, other org: its own entry
    assert a != b and s.find("entries", b) is None and s_b.find("entries", a) is None


def test_invalid_buyer_doc_does_not_lose_the_receivable(booking, s):
    entry_id = booking.book_receivable(ORG_A, **{**RECV, "counterparty_doc": "000.000.000-00"})
    assert s.find("entries", entry_id)["counterparty_doc"] is None


def test_bridge_input_is_validated(booking):
    with pytest.raises(FinanceError):
        booking.book_receivable(ORG_A, **{**RECV, "source": "teleport"})
    with pytest.raises(FinanceError):
        booking.book_receivable(ORG_A, **{**RECV, "source_ref": ""})


def test_book_settlement_is_idempotent_and_books_to_the_gateway_account(booking, s):
    booking.book_receivable(ORG_A, **RECV)
    args = dict(source="commerce_order", source_ref="order-1", kind="payment", external_ref="pay_9",
                amount_cents=10000, fee_cents=199, settled_on=date(2026, 10, 18))
    first = booking.book_settlement(ORG_A, **args)
    again = booking.book_settlement(ORG_A, **args)
    assert first == again and len(s.rows("settlements")) == 1
    gateway = [a for a in accounts.list_accounts(s) if a["kind"] == "gateway"]
    assert len(gateway) == 1 and gateway[0]["gateway"] == "asaas"  # created on demand, once
    assert accounts.account_balance(s, gateway[0]["id"], date(2026, 10, 31))["balance_cents"] == 10000 - 199
    entry = s.rows("entries")[0]
    assert (entry["status"], entry["settled_cents"]) == ("paid", 10000)


def test_book_settlement_refund_and_account_hints(booking, s):
    booking.book_receivable(ORG_A, **RECV)
    base = dict(source="commerce_order", source_ref="order-1", amount_cents=10000, fee_cents=0, settled_on=date(2026, 10, 18))
    booking.book_settlement(ORG_A, kind="payment", external_ref="pay_1", **base)
    booking.book_settlement(ORG_A, kind="refund", external_ref="ref_1", **{**base, "amount_cents": 2500})
    assert s.rows("entries")[0]["settled_cents"] == 7500
    bank = mk_account(s, "Banco")
    booking.book_receivable(ORG_A, **{**RECV, "source_ref": "order-2"})
    booking.book_settlement(ORG_A, kind="payment", external_ref="pay_2", account_hint=f"account:{bank['id']}",
                            **{**base, "source_ref": "order-2"})
    assert accounts.account_balance(s, bank["id"], date(2026, 10, 31))["balance_cents"] == 10000
    with pytest.raises(FinanceError):
        booking.book_settlement(ORG_A, kind="payment", external_ref="pay_3", account_hint="whatever", **base)


def test_book_settlement_needs_the_entry_and_a_ref(booking):
    base = dict(kind="payment", amount_cents=100, fee_cents=0, settled_on=date(2026, 10, 18))
    with pytest.raises(NotFoundError):
        booking.book_settlement(ORG_A, source="commerce_order", source_ref="ghost", external_ref="x", **base)
    booking.book_receivable(ORG_A, **RECV)
    with pytest.raises(FinanceError):
        booking.book_settlement(ORG_A, source="commerce_order", source_ref="order-1", external_ref="", **base)


def test_settlement_cannot_cross_tenants(booking, s_b):
    booking.book_receivable(ORG_A, **RECV)
    with pytest.raises(NotFoundError):  # org B asks to settle org A's order reference
        booking.book_settlement(ORG_B, source="commerce_order", source_ref="order-1", kind="payment",
                                external_ref="p", amount_cents=1, fee_cents=0, settled_on=date(2026, 10, 18))
    assert s_b.rows("settlements") == []


def test_noop_books_nothing_and_never_fails():
    noop = NoopFinanceBooking()
    assert noop.book_receivable(ORG_A, **RECV) is None
    assert noop.book_settlement(ORG_A, source="x", source_ref="y", kind="payment", external_ref="z",
                                amount_cents=1, fee_cents=0, settled_on=date(2026, 1, 1)) is None


def test_fake_has_the_same_idempotency_keys():
    fake = FakeFinanceBooking()
    a = fake.book_receivable(ORG_A, **RECV)
    assert fake.book_receivable(ORG_A, **RECV) == a and len(fake.entries) == 1
    args = dict(source="commerce_order", source_ref="order-1", kind="payment", external_ref="p1", amount_cents=1)
    s1 = fake.book_settlement(ORG_A, **args)
    assert fake.book_settlement(ORG_A, **args) == s1 and len(fake.settlements) == 1
    with pytest.raises(NotFoundError):
        fake.book_settlement(ORG_A, **{**args, "source_ref": "ghost"})
