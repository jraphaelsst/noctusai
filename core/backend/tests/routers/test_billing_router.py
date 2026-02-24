"""
Tests for Billing Router.

POST  /api/billing/checkout   (authenticated)
POST  /api/billing/webhook    (no auth, Stripe signature)
POST  /api/billing/portal     (authenticated)
GET   /api/billing/invoices   (authenticated)
GET   /api/billing/status     (authenticated)
"""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# POST /api/billing/checkout
# ---------------------------------------------------------------------------

class TestCreateCheckout:
    def test_checkout_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})

        with patch(
            "app.routers.billing.billing_service.start_subscription",
            return_value="https://checkout.stripe.com/session/123",
        ):
            resp = client.post("/api/billing/checkout", json={
                "plan_id": "plan-1",
                "billing_cycle": "monthly",
            })
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert "checkout_url" in data
            assert "stripe.com" in data["checkout_url"]

    def test_checkout_yearly(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})

        with patch(
            "app.routers.billing.billing_service.start_subscription",
            return_value="https://checkout.stripe.com/session/yearly-123",
        ):
            resp = client.post("/api/billing/checkout", json={
                "plan_id": "plan-1",
                "billing_cycle": "yearly",
            })
            assert resp.status_code == 200

    def test_checkout_invalid_billing_cycle(self, client):
        resp = client.post("/api/billing/checkout", json={
            "plan_id": "plan-1",
            "billing_cycle": "quarterly",
        })
        assert resp.status_code == 422

    def test_checkout_missing_plan_id(self, client):
        resp = client.post("/api/billing/checkout", json={
            "billing_cycle": "monthly",
        })
        assert resp.status_code == 422

    def test_checkout_profile_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = client.post("/api/billing/checkout", json={
            "plan_id": "plan-1",
            "billing_cycle": "monthly",
        })
        assert resp.status_code == 404

    def test_checkout_unauthenticated(self, unauth_client):
        resp = unauth_client.post("/api/billing/checkout", json={
            "plan_id": "plan-1",
            "billing_cycle": "monthly",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/billing/webhook
# ---------------------------------------------------------------------------

class TestStripeWebhook:
    def test_webhook_missing_signature(self, client):
        resp = client.raw().post(
            "/api/billing/webhook",
            content=b'{"type": "test"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_webhook_with_valid_signature(self, client):
        mock_event = {
            "id": "evt_123",
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_123", "metadata": {"org_id": "org-1"}}},
        }

        with patch(
            "app.routers.billing.stripe_service.construct_webhook_event",
            return_value=mock_event,
        ), patch(
            "app.routers.billing.billing_service.handle_checkout_completed",
        ), patch(
            "app.routers.billing._log_billing_event",
        ):
            resp = client.raw().post(
                "/api/billing/webhook",
                content=b'{"type": "checkout.session.completed"}',
                headers={
                    "Content-Type": "application/json",
                    "stripe-signature": "t=1234,v1=abc123",
                },
            )
            assert resp.status_code == 200
            assert resp.json()["received"] is True


# ---------------------------------------------------------------------------
# POST /api/billing/portal
# ---------------------------------------------------------------------------

class TestCreatePortal:
    def test_portal_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})

        mock_session = MagicMock()
        mock_session.url = "https://billing.stripe.com/portal/session/123"

        with patch(
            "app.routers.billing.billing_service.ensure_customer",
            return_value="cus_123",
        ), patch(
            "app.routers.billing.stripe_service.create_portal_session",
            return_value=mock_session,
        ):
            resp = client.post("/api/billing/portal", json={})
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert "portal_url" in data

    def test_portal_profile_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = client.post("/api/billing/portal", json={})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/billing/invoices
# ---------------------------------------------------------------------------

class TestListInvoices:
    def test_list_invoices_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("subscriptions", [
            {"stripe_customer_id": "cus_123"},
        ])

        mock_invoice = MagicMock()
        mock_invoice.id = "inv_123"
        mock_invoice.number = "INV-001"
        mock_invoice.status = "paid"
        mock_invoice.amount_due = 9900
        mock_invoice.amount_paid = 9900
        mock_invoice.currency = "brl"
        mock_invoice.period_start = 1700000000
        mock_invoice.period_end = 1702592000
        mock_invoice.hosted_invoice_url = "https://invoice.stripe.com/i/123"
        mock_invoice.invoice_pdf = "https://invoice.stripe.com/pdf/123"
        mock_invoice.created = 1700000000

        with patch(
            "app.routers.billing.stripe_service.get_invoices",
            return_value=[mock_invoice],
        ), patch(
            "app.routers.billing.billing_service.format_stripe_timestamp",
            return_value="2024-11-15T00:00:00Z",
        ):
            resp = client.get("/api/billing/invoices")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert isinstance(data, list)
            assert len(data) == 1

    def test_list_invoices_no_customer(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("subscriptions", [])

        resp = client.get("/api/billing/invoices")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_invoices_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/billing/invoices")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/billing/status
# ---------------------------------------------------------------------------

class TestBillingStatus:
    def test_billing_status_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})

        mock_status = {
            "plan": "Pro",
            "status": "active",
            "next_invoice": "2026-03-01",
        }

        with patch(
            "app.routers.billing.billing_service.get_billing_status",
            return_value=mock_status,
        ):
            resp = client.get("/api/billing/status")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["plan"] == "Pro"
            assert data["status"] == "active"

    def test_billing_status_profile_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = client.get("/api/billing/status")
        assert resp.status_code == 404

    def test_billing_status_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/billing/status")
        assert resp.status_code == 401
