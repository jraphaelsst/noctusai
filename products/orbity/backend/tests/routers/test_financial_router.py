"""
Auth-boundary + validation tests for the /api/financial/* router.

Auth: strict == 401 (not 404/422) for all protected endpoints.
Pydantic: extra="forbid" on inbound schemas → 422 for unknown fields.
"""
import pytest


TEST_ORG = "00000000-0000-0000-0000-000000000001"

# ---------------------------------------------------------------------------
# Auth-boundary: every endpoint must return EXACTLY 401 (no 404/422 shortcut)
# ---------------------------------------------------------------------------

class TestFinancialContractsAuth:
    """Every /api/financial/contracts/* endpoint requires authentication."""

    def test_list_contracts_without_auth_returns_401(self, client):
        assert client.raw().get("/api/financial/contracts").status_code == 401

    def test_create_contract_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/financial/contracts",
            json={
                "title": "Contrato Teste",
                "monthly_value": 1500.00,
                "start_date": "2026-01-01",
            },
        ).status_code == 401

    def test_get_contract_without_auth_returns_401(self, client):
        assert client.raw().get("/api/financial/contracts/some-id").status_code == 401

    def test_patch_contract_without_auth_returns_401(self, client):
        assert client.raw().patch(
            "/api/financial/contracts/some-id",
            json={"title": "updated"},
        ).status_code == 401

    def test_delete_contract_without_auth_returns_401(self, client):
        assert client.raw().delete("/api/financial/contracts/some-id").status_code == 401


class TestFinancialExpensesAuth:
    """Every /api/financial/expenses/* endpoint requires authentication."""

    def test_list_expenses_without_auth_returns_401(self, client):
        assert client.raw().get("/api/financial/expenses").status_code == 401

    def test_create_expense_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/financial/expenses",
            json={
                "description": "Licença SaaS",
                "amount": 99.90,
                "due_date": "2026-01-15",
            },
        ).status_code == 401

    def test_get_expense_without_auth_returns_401(self, client):
        assert client.raw().get("/api/financial/expenses/some-id").status_code == 401

    def test_patch_expense_without_auth_returns_401(self, client):
        assert client.raw().patch(
            "/api/financial/expenses/some-id",
            json={"paid": True},
        ).status_code == 401

    def test_delete_expense_without_auth_returns_401(self, client):
        assert client.raw().delete("/api/financial/expenses/some-id").status_code == 401


class TestFinancialRevenuesAuth:
    """Every /api/financial/revenues/* endpoint requires authentication."""

    def test_list_revenues_without_auth_returns_401(self, client):
        assert client.raw().get("/api/financial/revenues").status_code == 401

    def test_create_revenue_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/financial/revenues",
            json={
                "amount": 2000.00,
                "reference_month": "2026-01-01",
                "due_date": "2026-01-10",
            },
        ).status_code == 401

    def test_get_revenue_without_auth_returns_401(self, client):
        assert client.raw().get("/api/financial/revenues/some-id").status_code == 401

    def test_patch_revenue_without_auth_returns_401(self, client):
        assert client.raw().patch(
            "/api/financial/revenues/some-id",
            json={"status": "paid"},
        ).status_code == 401

    def test_delete_revenue_without_auth_returns_401(self, client):
        assert client.raw().delete("/api/financial/revenues/some-id").status_code == 401


class TestFinancialCashFlowAuth:
    """Cash-flow summary endpoint requires authentication."""

    def test_cash_flow_without_auth_returns_401(self, client):
        assert client.raw().get("/api/financial/cash-flow/2026-01-01").status_code == 401


# ---------------------------------------------------------------------------
# Pydantic validation (StrictHttpModel extra="forbid")
# ---------------------------------------------------------------------------

class TestFinancialContractValidation:
    """Inbound contract schema rejects unknown fields and invalid values."""

    def test_create_contract_extra_field_returns_422(self, client):
        resp = client.post(
            "/api/financial/contracts",
            json={
                "title": "Contrato",
                "monthly_value": 1000.0,
                "start_date": "2026-01-01",
                "rogue": True,
            },
        )
        assert resp.status_code == 422

    def test_create_contract_missing_title_returns_422(self, client):
        resp = client.post(
            "/api/financial/contracts",
            json={"monthly_value": 1000.0, "start_date": "2026-01-01"},
        )
        assert resp.status_code == 422

    def test_create_contract_negative_value_returns_422(self, client):
        resp = client.post(
            "/api/financial/contracts",
            json={"title": "X", "monthly_value": -1.0, "start_date": "2026-01-01"},
        )
        assert resp.status_code == 422

    def test_create_contract_invalid_status_returns_422(self, client):
        resp = client.post(
            "/api/financial/contracts",
            json={
                "title": "X",
                "monthly_value": 1000.0,
                "start_date": "2026-01-01",
                "status": "unknown",
            },
        )
        assert resp.status_code == 422

    def test_create_contract_billing_day_out_of_range_returns_422(self, client):
        resp = client.post(
            "/api/financial/contracts",
            json={
                "title": "X",
                "monthly_value": 1000.0,
                "start_date": "2026-01-01",
                "billing_day": 32,
            },
        )
        assert resp.status_code == 422

    def test_patch_contract_no_fields_returns_400(self, client):
        """Empty PATCH body → 400 before service layer."""
        resp = client.patch("/api/financial/contracts/some-id", json={})
        assert resp.status_code == 400


class TestFinancialExpenseValidation:
    """Inbound expense schema rejects unknown fields and invalid values."""

    def test_create_expense_extra_field_returns_422(self, client):
        resp = client.post(
            "/api/financial/expenses",
            json={
                "description": "X",
                "amount": 100.0,
                "due_date": "2026-01-15",
                "rogue": True,
            },
        )
        assert resp.status_code == 422

    def test_create_expense_zero_amount_returns_422(self, client):
        resp = client.post(
            "/api/financial/expenses",
            json={"description": "X", "amount": 0, "due_date": "2026-01-15"},
        )
        assert resp.status_code == 422

    def test_create_expense_invalid_recurrence_returns_422(self, client):
        resp = client.post(
            "/api/financial/expenses",
            json={
                "description": "X",
                "amount": 100.0,
                "due_date": "2026-01-15",
                "recurrence": "weekly",
            },
        )
        assert resp.status_code == 422

    def test_patch_expense_no_fields_returns_400(self, client):
        resp = client.patch("/api/financial/expenses/some-id", json={})
        assert resp.status_code == 400


class TestFinancialRevenueValidation:
    """Inbound revenue schema rejects unknown fields and invalid values."""

    def test_create_revenue_extra_field_returns_422(self, client):
        resp = client.post(
            "/api/financial/revenues",
            json={
                "amount": 1000.0,
                "reference_month": "2026-01-01",
                "due_date": "2026-01-10",
                "rogue": True,
            },
        )
        assert resp.status_code == 422

    def test_create_revenue_invalid_status_returns_422(self, client):
        resp = client.post(
            "/api/financial/revenues",
            json={
                "amount": 1000.0,
                "reference_month": "2026-01-01",
                "due_date": "2026-01-10",
                "status": "unknown",
            },
        )
        assert resp.status_code == 422

    def test_patch_revenue_no_fields_returns_400(self, client):
        resp = client.patch("/api/financial/revenues/some-id", json={})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Happy path (authenticated client — mock returns seeded data from conftest)
# ---------------------------------------------------------------------------

class TestFinancialContractsHappyPath:
    """With auth + mock DB: read endpoints work; missing rows → 404."""

    def test_list_contracts_authenticated_returns_200(self, client):
        resp = client.get("/api/financial/contracts")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body

    def test_get_contract_missing_returns_404(self, client):
        resp = client.get("/api/financial/contracts/does-not-exist")
        assert resp.status_code == 404

    def test_delete_contract_missing_returns_404(self, client):
        resp = client.delete("/api/financial/contracts/does-not-exist")
        assert resp.status_code == 404


class TestFinancialExpensesHappyPath:

    def test_list_expenses_authenticated_returns_200(self, client):
        resp = client.get("/api/financial/expenses")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body

    def test_get_expense_missing_returns_404(self, client):
        resp = client.get("/api/financial/expenses/does-not-exist")
        assert resp.status_code == 404

    def test_delete_expense_missing_returns_404(self, client):
        resp = client.delete("/api/financial/expenses/does-not-exist")
        assert resp.status_code == 404


class TestFinancialRevenuesHappyPath:

    def test_list_revenues_authenticated_returns_200(self, client):
        resp = client.get("/api/financial/revenues")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body

    def test_get_revenue_missing_returns_404(self, client):
        resp = client.get("/api/financial/revenues/does-not-exist")
        assert resp.status_code == 404

    def test_delete_revenue_missing_returns_404(self, client):
        resp = client.delete("/api/financial/revenues/does-not-exist")
        assert resp.status_code == 404


class TestFinancialCashFlowHappyPath:

    def test_cash_flow_authenticated_returns_200(self, client):
        resp = client.get("/api/financial/cash-flow/2026-01-01")
        assert resp.status_code == 200
        body = resp.json()
        # shape check — all keys present
        assert "reference_month" in body
        assert "paid_revenues" in body
        assert "paid_expenses" in body
        assert "net" in body
        assert "pending_revenues" in body
        assert "overdue_revenues" in body

    def test_cash_flow_response_has_correct_types(self, client):
        resp = client.get("/api/financial/cash-flow/2026-06-01")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["paid_revenues"], (int, float))
        assert isinstance(body["net"], (int, float))
