"""
Tests for the Clinic Financials Router.

Covers: clinic dashboard, create transfer, list transfers,
and auth/permission checks (clinic_admin only).
"""
import pytest

SAMPLE_WALLET = {
    "id": "wallet-clinic-001",
    "owner_id": "test-clinic-123",
    "owner_type": "clinic",
    "balance": "5000.00",
    "last_updated": "2026-04-01T10:00:00Z",
}

SAMPLE_TRANSACTION = {
    "id": "tx-001",
    "therapist_id": "therapist-001",
    "patient_id": "patient-001",
    "clinic_id": "test-clinic-123",
    "gross_amount": "200.00",
    "platform_fee_amount": "20.00",
    "clinic_share_amount": "36.00",
    "therapist_share_amount": "144.00",
    "status": "captured",
}

SAMPLE_TRANSFER = {
    "id": "transfer-001",
    "clinic_id": "test-clinic-123",
    "therapist_id": "therapist-001",
    "amount": 500.00,
    "reason": "Bonus mensal",
    "initiated_by_user_id": "test-user-123",
    "created_at": "2026-04-01T10:00:00Z",
}


class TestClinicDashboard:
    """GET /api/clinic/financials/"""

    def test_dashboard(self, clinic_admin_client):
        """Clinic admin gets financial dashboard."""
        clinic_admin_client._mock_supabase.set_table_data("wallets", [SAMPLE_WALLET])
        clinic_admin_client._mock_supabase.set_table_data("transactions", [SAMPLE_TRANSACTION])
        resp = clinic_admin_client.get("/api/clinic/financials/")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        data = body["data"]
        assert "wallet_balance" in data
        assert "total_gross" in data
        assert "therapist_breakdown" in data

    def test_dashboard_therapist_forbidden(self, client):
        """Therapist cannot access clinic dashboard."""
        resp = client.get("/api/clinic/financials/")
        assert resp.status_code == 403

    def test_dashboard_patient_forbidden(self, patient_client):
        """Patient cannot access clinic dashboard."""
        resp = patient_client.get("/api/clinic/financials/")
        assert resp.status_code == 403

    def test_dashboard_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/clinic/financials/")
        assert resp.status_code == 401


class TestCreateTransfer:
    """POST /api/clinic/financials/transfers"""

    def test_create_transfer(self, clinic_admin_client):
        """Clinic admin creates a voluntary transfer."""
        clinic_admin_client._mock_supabase.set_table_data("wallets", [SAMPLE_WALLET])
        clinic_admin_client._mock_supabase.set_table_data("wallet_movements", [])
        clinic_admin_client._mock_supabase.set_table_data("clinic_transfers", [SAMPLE_TRANSFER])
        resp = clinic_admin_client.post("/api/clinic/financials/transfers", json={
            "therapist_id": "therapist-001",
            "amount": "500.00",
            "reason": "Bonus mensal",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_create_transfer_invalid_amount(self, clinic_admin_client):
        """Amount of zero returns 422."""
        resp = clinic_admin_client.post("/api/clinic/financials/transfers", json={
            "therapist_id": "therapist-001",
            "amount": "0",
            "reason": "Teste",
        })
        assert resp.status_code == 422

    def test_create_transfer_therapist_forbidden(self, client):
        """Therapist cannot create clinic transfers."""
        resp = client.post("/api/clinic/financials/transfers", json={
            "therapist_id": "therapist-001",
            "amount": "100.00",
            "reason": "Teste",
        })
        assert resp.status_code == 403


class TestListTransfers:
    """GET /api/clinic/financials/transfers"""

    def test_list_transfers(self, clinic_admin_client):
        """Clinic admin lists transfer history."""
        clinic_admin_client._mock_supabase.set_table_data("clinic_transfers", [SAMPLE_TRANSFER])
        resp = clinic_admin_client.get("/api/clinic/financials/transfers")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_list_transfers_therapist_forbidden(self, client):
        """Therapist cannot list clinic transfers."""
        resp = client.get("/api/clinic/financials/transfers")
        assert resp.status_code == 403
