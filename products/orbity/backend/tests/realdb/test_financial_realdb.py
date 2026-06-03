"""
Real-DB integration tests for the Orbity financial-core organ.

Tests hit a real Supabase instance to verify:
  - FK constraints (client_id, contract_id → existing rows)
  - CHECK constraints (status, recurrence, billing_day, amount > 0)
  - Cascade behaviour (ON DELETE SET NULL for client_id/contract_id)
  - RLS org isolation: org A rows are invisible to an anon/wrong-org JWT
  - Full round-trip CRUD for contracts, expenses, revenues

Run only (requires migration 006 applied + Supabase credentials):
  pytest products/orbity/backend/tests/realdb/ -v -m realdb

Skip condition: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set.

PENDING-MIGRATION-APPLY: migration 006_financial_core.sql must be applied
to the live Supabase project by the tech-lead before these tests are run.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from postgrest.exceptions import APIError

pytestmark = pytest.mark.realdb


# ---------------------------------------------------------------------------
# Contracts — round-trip CRUD
# ---------------------------------------------------------------------------

class TestContractCRUD:
    """Full CRUD on orbity.contracts."""

    def test_contract_crud(self, fin_db, test_org, cleanup):
        # Create
        contract = fin_db.table("contracts").insert({
            "org_id": test_org["id"],
            "title": "Gestão de Redes Sociais",
            "monthly_value": 2500.00,
            "billing_day": 5,
            "start_date": date.today().isoformat(),
            "status": "active",
        }).execute().data[0]
        cleanup.append(("contracts", contract["id"]))

        assert contract["title"] == "Gestão de Redes Sociais"
        assert float(contract["monthly_value"]) == 2500.00
        assert contract["status"] == "active"
        assert contract["billing_day"] == 5

        # Read
        fetched = fin_db.table("contracts") \
            .select("*").eq("id", contract["id"]).single().execute().data
        assert fetched["org_id"] == test_org["id"]

        # Update — pause the contract
        fin_db.table("contracts") \
            .update({"status": "paused"}).eq("id", contract["id"]).execute()
        updated = fin_db.table("contracts") \
            .select("status").eq("id", contract["id"]).single().execute().data
        assert updated["status"] == "paused"

        # Delete
        fin_db.table("contracts").delete().eq("id", contract["id"]).execute()
        check = fin_db.table("contracts").select("id").eq("id", contract["id"]).execute().data
        assert check == []
        cleanup.pop()


class TestContractCheckConstraints:
    """CHECK constraints on contracts."""

    def test_invalid_status_rejected(self, fin_db, test_org):
        with pytest.raises(APIError):
            fin_db.table("contracts").insert({
                "org_id": test_org["id"],
                "title": "Bad Status",
                "monthly_value": 1000.00,
                "billing_day": 1,
                "start_date": date.today().isoformat(),
                "status": "invalid_status",
            }).execute()

    def test_negative_monthly_value_rejected(self, fin_db, test_org):
        with pytest.raises(APIError):
            fin_db.table("contracts").insert({
                "org_id": test_org["id"],
                "title": "Negative Value",
                "monthly_value": -100.00,
                "billing_day": 1,
                "start_date": date.today().isoformat(),
            }).execute()

    def test_billing_day_out_of_range_rejected(self, fin_db, test_org):
        with pytest.raises(APIError):
            fin_db.table("contracts").insert({
                "org_id": test_org["id"],
                "title": "Bad Day",
                "monthly_value": 1000.00,
                "billing_day": 32,
                "start_date": date.today().isoformat(),
            }).execute()


# ---------------------------------------------------------------------------
# Expenses — round-trip CRUD
# ---------------------------------------------------------------------------

class TestExpenseCRUD:
    """Full CRUD on orbity.expenses."""

    def test_expense_crud(self, fin_db, test_org, cleanup):
        # Create
        expense = fin_db.table("expenses").insert({
            "org_id": test_org["id"],
            "category": "software",
            "description": "Licença Adobe Creative Cloud",
            "amount": 299.90,
            "due_date": date.today().isoformat(),
            "recurrence": "monthly",
        }).execute().data[0]
        cleanup.append(("expenses", expense["id"]))

        assert expense["description"] == "Licença Adobe Creative Cloud"
        assert float(expense["amount"]) == 299.90
        assert expense["paid"] is False
        assert expense["recurrence"] == "monthly"

        # Mark as paid
        fin_db.table("expenses") \
            .update({"paid": True}).eq("id", expense["id"]).execute()
        updated = fin_db.table("expenses") \
            .select("paid").eq("id", expense["id"]).single().execute().data
        assert updated["paid"] is True

        # Delete
        fin_db.table("expenses").delete().eq("id", expense["id"]).execute()
        check = fin_db.table("expenses").select("id").eq("id", expense["id"]).execute().data
        assert check == []
        cleanup.pop()


class TestExpenseCheckConstraints:
    """CHECK constraints on expenses."""

    def test_invalid_recurrence_rejected(self, fin_db, test_org):
        with pytest.raises(APIError):
            fin_db.table("expenses").insert({
                "org_id": test_org["id"],
                "description": "Bad Recurrence",
                "amount": 100.00,
                "due_date": date.today().isoformat(),
                "recurrence": "weekly",
            }).execute()

    def test_zero_amount_rejected(self, fin_db, test_org):
        with pytest.raises(APIError):
            fin_db.table("expenses").insert({
                "org_id": test_org["id"],
                "description": "Zero",
                "amount": 0,
                "due_date": date.today().isoformat(),
            }).execute()


# ---------------------------------------------------------------------------
# Revenues — round-trip CRUD + FK
# ---------------------------------------------------------------------------

class TestRevenueCRUD:
    """Full CRUD on orbity.revenues."""

    def test_revenue_crud(self, fin_db, test_org, cleanup):
        # Create without client (nullable)
        revenue = fin_db.table("revenues").insert({
            "org_id": test_org["id"],
            "reference_month": "2026-01-01",
            "amount": 3000.00,
            "status": "pending",
            "due_date": "2026-01-10",
        }).execute().data[0]
        cleanup.append(("revenues", revenue["id"]))

        assert float(revenue["amount"]) == 3000.00
        assert revenue["status"] == "pending"
        assert revenue["client_id"] is None

        # Mark paid
        fin_db.table("revenues") \
            .update({"status": "paid"}).eq("id", revenue["id"]).execute()
        updated = fin_db.table("revenues") \
            .select("status").eq("id", revenue["id"]).single().execute().data
        assert updated["status"] == "paid"

        # Delete
        fin_db.table("revenues").delete().eq("id", revenue["id"]).execute()
        check = fin_db.table("revenues").select("id").eq("id", revenue["id"]).execute().data
        assert check == []
        cleanup.pop()


class TestRevenueCheckConstraints:
    """CHECK constraints on revenues."""

    def test_invalid_status_rejected(self, fin_db, test_org):
        with pytest.raises(APIError):
            fin_db.table("revenues").insert({
                "org_id": test_org["id"],
                "reference_month": "2026-01-01",
                "amount": 1000.00,
                "status": "bounced",
                "due_date": "2026-01-10",
            }).execute()

    def test_zero_amount_rejected(self, fin_db, test_org):
        with pytest.raises(APIError):
            fin_db.table("revenues").insert({
                "org_id": test_org["id"],
                "reference_month": "2026-01-01",
                "amount": 0,
                "status": "pending",
                "due_date": "2026-01-10",
            }).execute()

    def test_fk_invalid_client_rejected(self, fin_db, test_org):
        """client_id FK → orbity.clients — non-existent UUID must be rejected."""
        fake_client = str(uuid.uuid4())
        with pytest.raises(APIError):
            fin_db.table("revenues").insert({
                "org_id": test_org["id"],
                "client_id": fake_client,
                "reference_month": "2026-01-01",
                "amount": 1000.00,
                "status": "pending",
                "due_date": "2026-01-10",
            }).execute()


class TestRevenueFKToContract:
    """Revenue FK to contracts — SET NULL on contract delete."""

    def test_revenue_contract_fk_set_null_on_delete(self, fin_db, test_org, cleanup):
        # Create a contract
        contract = fin_db.table("contracts").insert({
            "org_id": test_org["id"],
            "title": "FK Test Contract",
            "monthly_value": 1000.00,
            "billing_day": 1,
            "start_date": date.today().isoformat(),
        }).execute().data[0]
        cleanup.append(("contracts", contract["id"]))

        # Create revenue linked to contract
        revenue = fin_db.table("revenues").insert({
            "org_id": test_org["id"],
            "contract_id": contract["id"],
            "reference_month": "2026-06-01",
            "amount": 1000.00,
            "status": "pending",
            "due_date": "2026-06-10",
        }).execute().data[0]
        cleanup.append(("revenues", revenue["id"]))

        # Delete contract → revenue.contract_id should become NULL (ON DELETE SET NULL)
        fin_db.table("contracts").delete().eq("id", contract["id"]).execute()
        cleanup.pop(-2)  # already deleted

        fetched = fin_db.table("revenues") \
            .select("contract_id").eq("id", revenue["id"]).single().execute().data
        assert fetched["contract_id"] is None


# ---------------------------------------------------------------------------
# RLS org isolation
# ---------------------------------------------------------------------------

class TestRLSOrgIsolation:
    """Rows written by org A must NOT be visible to an anon/wrong-org JWT.

    The anon key has no valid JWT claim → current_org_id() returns NULL →
    USING (org_id = public.current_org_id()) evaluates false for every row.
    This is the correct proof that RLS is not USING(true).
    """

    def test_contract_not_visible_under_anon_jwt(self, fin_db, anon_fin_db, test_org, cleanup):
        # Write via service_role (bypasses RLS)
        contract = fin_db.table("contracts").insert({
            "org_id": test_org["id"],
            "title": "RLS Isolation Test",
            "monthly_value": 1.00,
            "billing_day": 1,
            "start_date": date.today().isoformat(),
        }).execute().data[0]
        cleanup.append(("contracts", contract["id"]))

        # Read via anon key → should see 0 rows (RLS blocks)
        rows = anon_fin_db.table("contracts") \
            .select("id").eq("id", contract["id"]).execute().data
        assert rows == [], (
            "RLS FAILURE: anon JWT can see org A's contracts — "
            "policy must not be USING(true)"
        )

    def test_expense_not_visible_under_anon_jwt(self, fin_db, anon_fin_db, test_org, cleanup):
        expense = fin_db.table("expenses").insert({
            "org_id": test_org["id"],
            "description": "RLS Expense Test",
            "amount": 1.00,
            "due_date": date.today().isoformat(),
        }).execute().data[0]
        cleanup.append(("expenses", expense["id"]))

        rows = anon_fin_db.table("expenses") \
            .select("id").eq("id", expense["id"]).execute().data
        assert rows == [], "RLS FAILURE: anon JWT can see org A's expenses"

    def test_revenue_not_visible_under_anon_jwt(self, fin_db, anon_fin_db, test_org, cleanup):
        revenue = fin_db.table("revenues").insert({
            "org_id": test_org["id"],
            "reference_month": "2026-01-01",
            "amount": 1.00,
            "status": "pending",
            "due_date": date.today().isoformat(),
        }).execute().data[0]
        cleanup.append(("revenues", revenue["id"]))

        rows = anon_fin_db.table("revenues") \
            .select("id").eq("id", revenue["id"]).execute().data
        assert rows == [], "RLS FAILURE: anon JWT can see org A's revenues"
