"""
Tests for the Payments Router.

Covers: validate card, list payment methods, add payment method,
remove payment method, and auth checks.
"""
import pytest


class TestValidateCard:
    """POST /api/payments/validate-card"""

    def test_validate_card(self, patient_client):
        """Validate a card via phantom charge."""
        resp = patient_client.post("/api/payments/validate-card", json={
            "payment_method_id": "pm_test_123",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_validate_card_missing_id(self, patient_client):
        """Missing payment_method_id returns 422."""
        resp = patient_client.post("/api/payments/validate-card", json={})
        assert resp.status_code == 422

    def test_validate_card_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/payments/validate-card", json={
            "payment_method_id": "pm_test_123",
        })
        assert resp.status_code == 401


class TestListPaymentMethods:
    """GET /api/payments/methods"""

    def test_list_methods(self, patient_client):
        """List saved payment methods (stub returns empty list)."""
        resp = patient_client.get("/api/payments/methods")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert body["data"] == []

    def test_list_methods_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/payments/methods")
        assert resp.status_code == 401


class TestAddPaymentMethod:
    """POST /api/payments/methods"""

    def test_add_method(self, patient_client):
        """Add a payment method (stub)."""
        resp = patient_client.post("/api/payments/methods", json={
            "stripe_payment_method_id": "pm_test_456",
            "is_default": True,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert body["data"]["attached"] is True
        assert body["data"]["is_default"] is True

    def test_add_method_missing_id(self, patient_client):
        """Missing stripe_payment_method_id returns 422."""
        resp = patient_client.post("/api/payments/methods", json={
            "is_default": True,
        })
        assert resp.status_code == 422


class TestRemovePaymentMethod:
    """DELETE /api/payments/methods/:id"""

    def test_remove_method(self, patient_client):
        """Remove a payment method (stub)."""
        resp = patient_client.delete("/api/payments/methods/pm_test_456")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert body["data"]["detached"] is True

    def test_remove_method_401(self, client):
        """No auth returns 401."""
        resp = client._tc.delete("/api/payments/methods/pm_test_456")
        assert resp.status_code == 401
