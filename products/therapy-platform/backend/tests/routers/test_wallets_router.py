"""
Tests for the Wallets Router.

Covers: get own wallet, list movements, top up, withdraw,
and auth checks.
"""
import pytest

SAMPLE_WALLET = {
    "id": "wallet-001",
    "owner_id": "test-user-123",
    "owner_type": "patient",
    "balance": "100.00",
    "last_updated": "2026-04-01T10:00:00Z",
}

SAMPLE_MOVEMENT = {
    "id": "mov-001",
    "wallet_id": "wallet-001",
    "amount": "50.00",
    "type": "credit",
    "reference_type": "top_up",
    "description": "Recarga via cartao",
    "created_at": "2026-04-01T10:00:00Z",
}


class TestGetMyWallet:
    """GET /api/wallets/me"""

    def test_get_own_wallet(self, patient_client):
        """Patient gets own wallet."""
        patient_client._mock_supabase.set_table_data("wallets", [SAMPLE_WALLET])
        resp = patient_client.get("/api/wallets/me")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_get_wallet_therapist(self, client):
        """Therapist gets own wallet."""
        client._mock_supabase.set_table_data("wallets", [{
            **SAMPLE_WALLET,
            "owner_type": "therapist",
        }])
        resp = client.get("/api/wallets/me")
        assert resp.status_code == 200

    def test_get_wallet_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/wallets/me")
        assert resp.status_code == 401


class TestListMyMovements:
    """GET /api/wallets/me/movements"""

    def test_list_movements(self, patient_client):
        """Patient lists wallet movements."""
        patient_client._mock_supabase.set_table_data("wallets", [SAMPLE_WALLET])
        patient_client._mock_supabase.set_table_data("wallet_movements", [SAMPLE_MOVEMENT])
        resp = patient_client.get("/api/wallets/me/movements")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_list_movements_pagination(self, patient_client):
        """Pagination params accepted."""
        patient_client._mock_supabase.set_table_data("wallets", [SAMPLE_WALLET])
        patient_client._mock_supabase.set_table_data("wallet_movements", [])
        resp = patient_client.get("/api/wallets/me/movements?page=1&page_size=5")
        assert resp.status_code == 200


class TestTopUp:
    """POST /api/wallets/top-up"""

    def test_top_up(self, patient_client):
        """Patient tops up wallet."""
        patient_client._mock_supabase.set_table_data("wallets", [SAMPLE_WALLET])
        patient_client._mock_supabase.set_table_data("wallet_movements", [SAMPLE_MOVEMENT])
        resp = patient_client.post("/api/wallets/top-up", json={
            "amount": "50.00",
            "payment_method_id": "pm_test_123",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_top_up_invalid_amount(self, patient_client):
        """Amount below minimum returns 422."""
        resp = patient_client.post("/api/wallets/top-up", json={
            "amount": "0.50",
            "payment_method_id": "pm_test_123",
        })
        assert resp.status_code == 422

    def test_top_up_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/wallets/top-up", json={
            "amount": "50.00",
            "payment_method_id": "pm_test_123",
        })
        assert resp.status_code == 401


class TestWithdraw:
    """POST /api/wallets/withdraw"""

    def test_withdraw(self, client):
        """Therapist requests a withdrawal."""
        client._mock_supabase.set_table_data("wallets", [{
            **SAMPLE_WALLET,
            "owner_type": "therapist",
            "balance": "500.00",
        }])
        client._mock_supabase.set_table_data("wallet_movements", [SAMPLE_MOVEMENT])
        client._mock_supabase.set_table_data("payouts", [{
            "id": "payout-001",
            "recipient_id": "test-user-123",
            "recipient_type": "therapist",
            "amount": "100.00",
            "net_amount": "98.00",
            "fee_amount": "2.00",
            "status": "pending",
        }])
        client._mock_supabase.set_table_data("platform_settings", [])
        client._mock_supabase.set_table_data("therapist_settings", [])
        resp = client.post("/api/wallets/withdraw", json={
            "amount": "100.00",
        })
        assert resp.status_code == 200

    def test_withdraw_below_minimum(self, client):
        """Amount below minimum returns 422."""
        resp = client.post("/api/wallets/withdraw", json={
            "amount": "5.00",
        })
        assert resp.status_code == 422
