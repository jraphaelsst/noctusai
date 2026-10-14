"""The pure schedule: dates, amounts, the retainer excess rule, readjustment arithmetic."""
from __future__ import annotations

from datetime import date

from noctusai_lib.domain.contracts import documents, schedule as sch


def c(**over):
    base = {"id": "c1", "title": "Contrato", "billing_model": "recurring", "amount_cents": 100000, "frequency": "monthly",
            "due_day": 31, "first_due_date": "2026-01-31"}
    return {**base, **over}


def test_monthly_periods_keep_the_anchor_day_clamped():
    got = [i.due_date for i in sch.periods(c(), limit=4)]
    assert got == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


def test_quarterly_and_yearly_steps():
    q = [i.due_date for i in sch.periods(c(frequency="quarterly", due_day=15, first_due_date="2026-01-15"), limit=3)]
    assert q == [date(2026, 1, 15), date(2026, 4, 15), date(2026, 7, 15)]
    y = [i.due_date for i in sch.periods(c(frequency="yearly", due_day=15, first_due_date="2026-01-15"), limit=2)]
    assert y == [date(2026, 1, 15), date(2027, 1, 15)]


def test_periods_stop_at_end_date():
    assert len(list(sch.periods(c(end_date="2026-03-31")))) == 3


def test_installments_split_with_remainder_on_the_last():
    items = sch.finite_schedule(c(billing_model="installments", installments_count=3, amount_cents=100000, due_day=None,
                                  first_due_date="2026-01-10"))
    assert [i.amount_cents for i in items] == [33333, 33333, 33334]
    assert [i.period_key for i in items] == ["i1", "i2", "i3"]
    assert items[1].due_date == date(2026, 2, 10)


def test_one_time_is_a_single_item():
    items = sch.finite_schedule(c(billing_model="one_time", first_due_date="2026-05-05"))
    assert len(items) == 1 and items[0].due_date == date(2026, 5, 5)


def test_excess_rounds_half_up_to_the_cent_and_is_zero_inside_the_franchise():
    r = c(billing_model="retainer", retainer_minutes=600, excess_rate_cents=10000)
    assert sch.excess_cents(r, 600) == 0
    assert sch.excess_cents(r, 540) == 0
    assert sch.excess_cents(r, 690) == 15000  # 90 min over x R$100/h
    assert sch.excess_cents(c(retainer_minutes=0, excess_rate_cents=1), 1) == 0  # 1/60 cent rounds down
    assert sch.excess_cents(c(retainer_minutes=0, excess_rate_cents=1), 30) == 1  # 0.5 rounds up
    item = sch.excess_item(r, date(2026, 3, 1), 690)
    assert item and item.period_key == "2026-03" and item.kind == "excess" and item.due_date == date(2026, 4, 30)


def test_preview_skips_billed_and_remaining_value_counts_only_the_future():
    cc = c(billing_model="installments", installments_count=4, amount_cents=40000, due_day=None, first_due_date="2026-01-10")
    assert [i.period_key for i in sch.preview(cc, {"i1", "i2"}, 5)] == ["i3", "i4"]
    assert sch.remaining_value(cc, date(2026, 2, 10)) == 20000  # i3 + i4 (i2 is due ON the date)


def test_brl_formatting():
    assert documents.brl(123456) == "R$ 1.234,56"
    assert documents.brl(5) == "R$ 0,05"
    assert documents.brl(100000000) == "R$ 1.000.000,00"
