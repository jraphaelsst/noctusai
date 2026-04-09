"""
Tests for the Transactions Router.

Covers: list transactions (role-scoped), get transaction detail,
filters, pagination, and auth checks.
"""
import pytest

SAMPLE_TRANSACTION = {
    "id": "tx-001",
    "therapist_id": "test-user-123",
    "patient_id": "patient-001",
    "clinic_id": None,
    "gross_amount": "150.00",
    "platform_fee_amount": "15.00",
    "clinic_share_amount": None,
    "therapist_share_amount": "135.00",
    "status": "captured",
    "created_at": "2026-04-01T10:00:00Z",
}


class TestListTransactions:
    """GET /api/transactions/"""

    def test_list_transactions_therapist(self, client):
        """Therapist lists own transactions."""
        client._mock_supabase.set_table_data("transactions", [SAMPLE_TRANSACTION])
        resp = client.get("/api/transactions/")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_list_transactions_with_filters(self, client):
        """Filter by status query param."""
        client._mock_supabase.set_table_data("transactions", [SAMPLE_TRANSACTION])
        resp = client.get("/api/transactions/?status=captured")
        assert resp.status_code == 200

    def test_list_transactions_pagination(self, client):
        """Pagination params accepted."""
        client._mock_supabase.set_table_data("transactions", [])
        resp = client.get("/api/transactions/?page=1&page_size=5")
        assert resp.status_code == 200

    def test_list_transactions_patient(self, patient_client):
        """Patient lists own transactions."""
        patient_client._mock_supabase.set_table_data("transactions", [{
            **SAMPLE_TRANSACTION,
            "patient_id": "test-user-123",
        }])
        resp = patient_client.get("/api/transactions/")
        assert resp.status_code == 200

    def test_list_transactions_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/transactions/")
        assert resp.status_code == 401


class TestGetTransaction:
    """GET /api/transactions/:id"""

    def test_get_transaction_detail(self, client):
        """Therapist gets transaction detail."""
        client._mock_supabase.set_table_data("transactions", [SAMPLE_TRANSACTION])
        resp = client.get("/api/transactions/tx-001")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_get_transaction_not_found(self, client):
        """Non-existent transaction returns 404."""
        client._mock_supabase.set_table_data("transactions", [])
        resp = client.get("/api/transactions/nonexistent")
        assert resp.status_code == 404

    def test_get_transaction_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/transactions/tx-001")
        assert resp.status_code == 401
