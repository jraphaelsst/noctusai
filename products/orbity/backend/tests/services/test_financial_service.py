"""
Tests for FinancialService — contracts, expenses, revenues CRUD +
monthly cash-flow summary.

No monkeypatching of our own code.
read-side:  MockSupabaseClient(data=[...])
write-side: inserted_payloads / updated_payloads (read via MockRequestBuilder)
"""
from __future__ import annotations

from uuid import UUID

import pytest
from noctusai_lib.testing import MockSupabaseClient

from app.services.financial_service import FinancialService

ORG = UUID("00000000-0000-0000-0000-000000000888")


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _contract(
    id_="c-1",
    title="Contrato Alpha",
    monthly_value=1500.0,
    billing_day=5,
    start_date="2026-01-01",
    status="active",
):
    return {
        "id": id_,
        "org_id": str(ORG),
        "client_id": None,
        "title": title,
        "monthly_value": monthly_value,
        "billing_day": billing_day,
        "start_date": start_date,
        "end_date": None,
        "status": status,
        "notes": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _expense(
    id_="e-1",
    description="Adobe CC",
    amount=199.90,
    due_date="2026-01-20",
    paid=False,
    recurrence="none",
):
    return {
        "id": id_,
        "org_id": str(ORG),
        "category": "software",
        "description": description,
        "amount": amount,
        "due_date": due_date,
        "paid": paid,
        "paid_at": None,
        "recurrence": recurrence,
        "installments_total": None,
        "installment_n": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _revenue(
    id_="r-1",
    client_id=None,
    amount=2000.0,
    reference_month="2026-01-01",
    status="pending",
    due_date="2026-01-10",
):
    return {
        "id": id_,
        "org_id": str(ORG),
        "client_id": client_id,
        "contract_id": None,
        "reference_month": reference_month,
        "amount": amount,
        "status": status,
        "due_date": due_date,
        "paid_at": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _svc(rows=None):
    db = MockSupabaseClient(data=rows, schema="orbity")
    return db, FinancialService(db, org_id=ORG)


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

class TestContractCreate:
    def test_stamps_org_id(self):
        db, svc = _svc([])
        svc.create_contract({"title": "New", "monthly_value": 1000.0, "start_date": "2026-01-01"})
        inserted = db.table("contracts").inserted_payloads
        assert any(p.get("org_id") == str(ORG) and p.get("title") == "New" for p in inserted)

    def test_returns_inserted_row(self):
        db, svc = _svc([])
        row = svc.create_contract({"title": "New", "monthly_value": 1000.0, "start_date": "2026-01-01"})
        assert row["title"] == "New"


class TestContractGet:
    def test_get_existing(self):
        _db, svc = _svc([_contract(id_="c-9")])
        row = svc.get_contract("c-9")
        assert row is not None
        assert row["id"] == "c-9"

    def test_get_missing_returns_none(self):
        _db, svc = _svc([])
        assert svc.get_contract("nope") is None


class TestContractUpdate:
    def test_update_patches_row(self):
        db, svc = _svc([_contract(id_="c-1", title="Old")])
        updated = svc.update_contract("c-1", {"title": "New"})
        assert updated is not None
        assert any(p.get("title") == "New" for p in db.table("contracts").updated_payloads)

    def test_update_strips_org_id(self):
        db, svc = _svc([_contract(id_="c-1")])
        svc.update_contract("c-1", {"title": "ok", "org_id": "hacker"})
        updated = db.table("contracts").updated_payloads
        assert not any(p.get("org_id") == "hacker" for p in updated)

    def test_update_missing_returns_none(self):
        _db, svc = _svc([])
        assert svc.update_contract("ghost", {"title": "x"}) is None


class TestContractDelete:
    def test_delete_returns_true_when_found(self):
        _db, svc = _svc([_contract(id_="c-1")])
        assert svc.delete_contract("c-1") is True

    def test_delete_returns_false_when_missing(self):
        _db, svc = _svc([])
        assert svc.delete_contract("ghost") is False


class TestContractList:
    def test_list_returns_paginated_shape(self):
        rows = [_contract(f"c-{i}") for i in range(3)]
        _db, svc = _svc(rows)
        result = svc.list_contracts()
        assert "items" in result
        assert "total" in result
        assert "page" in result


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

class TestExpenseCreate:
    def test_stamps_org_id(self):
        db, svc = _svc([])
        svc.create_expense({"description": "Licença", "amount": 99.0, "due_date": "2026-01-20"})
        inserted = db.table("expenses").inserted_payloads
        assert any(p.get("org_id") == str(ORG) for p in inserted)

    def test_returns_inserted_row(self):
        _db, svc = _svc([])
        row = svc.create_expense({"description": "X", "amount": 50.0, "due_date": "2026-01-15"})
        assert row["description"] == "X"


class TestExpenseGet:
    def test_get_existing(self):
        _db, svc = _svc([_expense(id_="e-9")])
        row = svc.get_expense("e-9")
        assert row is not None
        assert row["id"] == "e-9"

    def test_get_missing_returns_none(self):
        _db, svc = _svc([])
        assert svc.get_expense("nope") is None


class TestExpenseUpdate:
    def test_update_patches_paid_flag(self):
        db, svc = _svc([_expense(id_="e-1", paid=False)])
        updated = svc.update_expense("e-1", {"paid": True})
        assert updated is not None
        assert any(p.get("paid") is True for p in db.table("expenses").updated_payloads)

    def test_update_strips_org_id(self):
        db, svc = _svc([_expense(id_="e-1")])
        svc.update_expense("e-1", {"description": "ok", "org_id": "hacker"})
        assert not any(p.get("org_id") == "hacker" for p in db.table("expenses").updated_payloads)

    def test_update_missing_returns_none(self):
        _db, svc = _svc([])
        assert svc.update_expense("ghost", {"paid": True}) is None


class TestExpenseDelete:
    def test_delete_returns_true_when_found(self):
        _db, svc = _svc([_expense(id_="e-1")])
        assert svc.delete_expense("e-1") is True

    def test_delete_returns_false_when_missing(self):
        _db, svc = _svc([])
        assert svc.delete_expense("ghost") is False


# ---------------------------------------------------------------------------
# Revenues
# ---------------------------------------------------------------------------

class TestRevenueCreate:
    def test_stamps_org_id(self):
        db, svc = _svc([])
        svc.create_revenue({"amount": 2000.0, "reference_month": "2026-01-01", "due_date": "2026-01-10"})
        inserted = db.table("revenues").inserted_payloads
        assert any(p.get("org_id") == str(ORG) for p in inserted)

    def test_returns_inserted_row(self):
        _db, svc = _svc([])
        row = svc.create_revenue({"amount": 1500.0, "reference_month": "2026-02-01", "due_date": "2026-02-05"})
        assert row["amount"] == 1500.0


class TestRevenueGet:
    def test_get_existing(self):
        _db, svc = _svc([_revenue(id_="r-9")])
        row = svc.get_revenue("r-9")
        assert row is not None
        assert row["id"] == "r-9"

    def test_get_missing_returns_none(self):
        _db, svc = _svc([])
        assert svc.get_revenue("nope") is None


class TestRevenueUpdate:
    def test_update_status_to_paid(self):
        db, svc = _svc([_revenue(id_="r-1", status="pending")])
        updated = svc.update_revenue("r-1", {"status": "paid"})
        assert updated is not None
        assert any(p.get("status") == "paid" for p in db.table("revenues").updated_payloads)

    def test_update_strips_org_id(self):
        db, svc = _svc([_revenue(id_="r-1")])
        svc.update_revenue("r-1", {"status": "paid", "org_id": "hacker"})
        assert not any(p.get("org_id") == "hacker" for p in db.table("revenues").updated_payloads)

    def test_update_missing_returns_none(self):
        _db, svc = _svc([])
        assert svc.update_revenue("ghost", {"status": "paid"}) is None


class TestRevenueDelete:
    def test_delete_returns_true_when_found(self):
        _db, svc = _svc([_revenue(id_="r-1")])
        assert svc.delete_revenue("r-1") is True

    def test_delete_returns_false_when_missing(self):
        _db, svc = _svc([])
        assert svc.delete_revenue("ghost") is False


# ---------------------------------------------------------------------------
# Monthly cash-flow summary
# ---------------------------------------------------------------------------

class TestMonthlyCashFlow:
    """The MockSupabaseClient returns ALL seeded rows for every table.

    We seed revenues and expenses directly in the mock client's data store.
    The service queries both tables and aggregates by paid/status.
    """

    def test_cash_flow_sums_paid_revenues(self):
        rows = [
            _revenue(id_="r-1", amount=1000.0, status="paid",    reference_month="2026-01-01"),
            _revenue(id_="r-2", amount=500.0,  status="paid",    reference_month="2026-01-01"),
            _revenue(id_="r-3", amount=200.0,  status="pending", reference_month="2026-01-01"),
        ]
        _db, svc = _svc(rows)
        result = svc.monthly_cash_flow("2026-01-01")
        assert result["paid_revenues"] == 1500.0

    def test_cash_flow_sums_paid_expenses(self):
        rows = [
            _expense(id_="e-1", amount=300.0, paid=True,  due_date="2026-01-10"),
            _expense(id_="e-2", amount=100.0, paid=False, due_date="2026-01-15"),
        ]
        _db, svc = _svc(rows)
        result = svc.monthly_cash_flow("2026-01-01")
        assert result["paid_expenses"] == 300.0

    def test_cash_flow_net_is_difference(self):
        rev_rows = [_revenue(id_="r-1", amount=2000.0, status="paid", reference_month="2026-02-01")]
        exp_rows = [_expense(id_="e-1", amount=500.0, paid=True, due_date="2026-02-10")]
        _db, svc = _svc(rev_rows + exp_rows)
        result = svc.monthly_cash_flow("2026-02-01")
        assert result["net"] == pytest.approx(1500.0)

    def test_cash_flow_pending_revenues_bucket(self):
        rows = [
            _revenue(id_="r-1", amount=800.0,  status="pending", reference_month="2026-03-01"),
            _revenue(id_="r-2", amount=200.0,  status="overdue", reference_month="2026-03-01"),
        ]
        _db, svc = _svc(rows)
        result = svc.monthly_cash_flow("2026-03-01")
        assert result["pending_revenues"] == 800.0
        assert result["overdue_revenues"] == 200.0

    def test_cash_flow_empty_month_returns_zeros(self):
        _db, svc = _svc([])
        result = svc.monthly_cash_flow("2026-04-01")
        assert result["paid_revenues"] == 0.0
        assert result["paid_expenses"] == 0.0
        assert result["net"] == 0.0

    def test_cash_flow_invalid_month_raises(self):
        _db, svc = _svc([])
        with pytest.raises(ValueError):
            svc.monthly_cash_flow("not-a-date")

    def test_cash_flow_reference_month_in_result(self):
        _db, svc = _svc([])
        result = svc.monthly_cash_flow("2026-05-01")
        assert result["reference_month"] == "2026-05-01"
