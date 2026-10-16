"""The cash-flow rule that makes "inactivate a client but keep a charge" mean something (upstream
``shouldIncludeOpenPayment``), and the month summary built on it.

Paid ALWAYS counts (immutable history), cancelled NEVER, an open charge counts when it was KEPT after the client's
inactivation or the client was still active in that month.
"""
from datetime import date

import pytest
from noctusai_lib.testing import MockSupabaseClient

from app.services.financial_service import (
    FinancialService,
    month_bounds,
    should_include_open_payment,
    was_client_active_in_month,
)

OCT = date(2026, 10, 1)
ORG = "00000000-0000-0000-0000-000000000abc"

ACTIVE = {"active": True, "inactivated_at": None}
INACTIVE_IN_SEPTEMBER = {"active": False, "inactivated_at": "2026-09-21T17:10:40+00:00"}
INACTIVE_IN_NOVEMBER = {"active": False, "inactivated_at": "2026-11-05T09:00:00+00:00"}
INACTIVE_UNKNOWN_DATE = {"active": False, "inactivated_at": None}


class TestShouldIncludeOpenPayment:
    @pytest.mark.parametrize("client", [ACTIVE, INACTIVE_IN_SEPTEMBER, INACTIVE_UNKNOWN_DATE, None])
    @pytest.mark.parametrize("preserved", [True, False])
    def test_paid_always_counts(self, client, preserved):
        assert should_include_open_payment("paid", preserved, client, OCT) is True

    @pytest.mark.parametrize("client", [ACTIVE, INACTIVE_IN_SEPTEMBER, None])
    @pytest.mark.parametrize("preserved", [True, False])
    def test_cancelled_never_counts(self, client, preserved):
        assert should_include_open_payment("cancelled", preserved, client, OCT) is False

    @pytest.mark.parametrize("status", ["open", "partial"])
    def test_a_kept_charge_counts_after_the_client_was_inactivated(self, status):
        assert should_include_open_payment(status, True, INACTIVE_IN_SEPTEMBER, OCT) is True

    def test_an_unkept_open_charge_of_an_inactivated_client_does_not_count(self):
        assert should_include_open_payment("open", False, INACTIVE_IN_SEPTEMBER, OCT) is False

    def test_an_open_charge_of_an_active_client_counts(self):
        assert should_include_open_payment("open", False, ACTIVE, OCT) is True

    def test_an_open_charge_counts_for_a_month_the_client_was_still_active_in(self):
        assert should_include_open_payment("open", False, INACTIVE_IN_NOVEMBER, OCT) is True

    def test_an_inactive_client_with_no_recorded_date_was_never_active_in_any_month(self):
        assert should_include_open_payment("open", False, INACTIVE_UNKNOWN_DATE, OCT) is False

    def test_a_receivable_with_no_client_counts(self):
        # Typed straight into the finance page: nobody to be inactive.
        assert should_include_open_payment("open", False, None, OCT) is True


def test_inactivated_on_the_last_day_of_the_month_was_still_active_that_month_only_after_it_ended():
    on_the_last_day = {"active": False, "inactivated_at": "2026-10-31T12:00:00+00:00"}
    assert was_client_active_in_month(on_the_last_day, OCT) is False
    assert was_client_active_in_month({"active": False, "inactivated_at": "2026-11-01T00:00:00+00:00"}, OCT) is True


def test_month_bounds():
    assert month_bounds("2026-10-17") == (date(2026, 10, 1), date(2026, 11, 1))
    assert month_bounds("2026-12") == (date(2026, 12, 1), date(2027, 1, 1))
    with pytest.raises(ValueError):
        month_bounds("not-a-month")


def _entry(i, direction, status, cents, due="2026-10-10", settled=None):
    return {"id": f"e{i}", "org_id": ORG, "direction": direction, "status": status, "amount_cents": cents,
            "settled_cents": cents if status == "paid" else (settled or 0), "due_date": due, "competence_month": "2026-10-01"}


def _charge(i, client_id, preserved=False):
    return {"id": f"ch{i}", "org_id": ORG, "entry_id": f"e{i}", "client_id": client_id, "preserved_after_deactivation": preserved}


def test_monthly_cash_flow_applies_the_rule_end_to_end():
    db = MockSupabaseClient(schema="orbity")
    db.set_table_data("fin_entries", [
        _entry(1, "receivable", "paid", 100_000),                       # paid -> counts (client inactivated)
        _entry(2, "receivable", "open", 50_000, due="2026-10-05"),      # kept -> counts as overdue (past due)
        _entry(3, "receivable", "open", 70_000, due="2099-01-01"),      # inactivated client, not kept -> out
        _entry(4, "receivable", "cancelled", 90_000),                   # cancelled -> out
        _entry(5, "receivable", "open", 20_000, due="2099-01-01"),      # active client -> pending
        _entry(6, "receivable", "open", 10_000, due="2099-01-01"),      # no client -> pending
        _entry(7, "payable", "paid", 30_000),
        _entry(8, "payable", "open", 99_000),
    ])
    db.set_table_data("billing_charges", [
        _charge(1, "c-gone"), _charge(2, "c-gone", preserved=True), _charge(3, "c-gone"), _charge(4, "c-gone"), _charge(5, "c-live"),
    ])
    db.set_table_data("clients", [
        {"id": "c-gone", "org_id": ORG, "active": False, "inactivated_at": "2026-09-21T17:10:40+00:00"},
        {"id": "c-live", "org_id": ORG, "active": True, "inactivated_at": None},
    ])
    out = FinancialService(db, ORG).monthly_cash_flow("2026-10-01")
    assert out == {
        "reference_month": "2026-10-01", "paid_revenues": 1000.0, "paid_expenses": 300.0, "net": 700.0,
        "pending_revenues": 300.0, "overdue_revenues": 500.0,
    }


def test_cash_flow_is_org_scoped():
    db = MockSupabaseClient(schema="orbity")
    db.set_table_data("fin_entries", [{**_entry(1, "receivable", "paid", 100_000), "org_id": "another-org"}])
    db.set_table_data("billing_charges", [])
    db.set_table_data("clients", [])
    assert FinancialService(db, ORG).monthly_cash_flow("2026-10-01")["paid_revenues"] == 0.0
