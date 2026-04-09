"""
Tests for the Admin Financials Router.

Covers: global dashboard, list all wallets, set commission override,
list payouts, process payout, and auth/permission checks (platform_admin only).
"""
import pytest

SAMPLE_TRANSACTION = {
    "id": "tx-001",
    "gross_amount": "200.00",
    "platform_fee_amount": "20.00",
    "clinic_share_amount": "36.00",
    "therapist_share_amount": "144.00",
    "status": "captured",
}

SAMPLE_PAYOUT = {
    "id": "payout-001",
    "recipient_id": "therapist-001",
    "recipient_type": "therapist",
    "amount": "500.00",
    "net_amount": "490.00",
    "fee_amount": "10.00",
    "status": "pending",
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_WALLET = {
    "id": "wallet-001",
    "owner_id": "therapist-001",
    "owner_type": "therapist",
    "balance": "1000.00",
    "last_updated": "2026-04-01T10:00:00Z",
}

SAMPLE_COMMISSION_OVERRIDE = {
    "id": "override-001",
    "target_type": "clinic",
    "target_id": "clinic-001",
    "custom_commission_pct": 8.0,
}

SAMPLE_REFUND = {
    "id": "ref-001",
    "refund_amount": "50.00",
    "status": "pending",
}


class TestGlobalDashboard:
    """GET /api/admin/financials/"""

    def test_dashboard(self, admin_client):
        """Platform admin gets global financial dashboard."""
        admin_client._mock_supabase.set_table_data("transactions", [SAMPLE_TRANSACTION])
        admin_client._mock_supabase.set_table_data("payouts", [SAMPLE_PAYOUT])
        admin_client._mock_supabase.set_table_data("refund_requests", [SAMPLE_REFUND])
        resp = admin_client.get("/api/admin/financials/")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        data = body["data"]
        assert "transactions" in data
        assert "payouts" in data
        assert "refunds" in data

    def test_dashboard_therapist_forbidden(self, client):
        """Therapist cannot access admin dashboard."""
        resp = client.get("/api/admin/financials/")
        assert resp.status_code == 403

    def test_dashboard_patient_forbidden(self, patient_client):
        """Patient cannot access admin dashboard."""
        resp = patient_client.get("/api/admin/financials/")
        assert resp.status_code == 403

    def test_dashboard_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/admin/financials/")
        assert resp.status_code == 401


class TestListAllWallets:
    """GET /api/admin/financials/wallets"""

    def test_list_all_wallets(self, admin_client):
        """Admin lists all wallets."""
        admin_client._mock_supabase.set_table_data("wallets", [SAMPLE_WALLET])
        resp = admin_client.get("/api/admin/financials/wallets")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_list_wallets_with_filter(self, admin_client):
        """Filter by owner_type."""
        admin_client._mock_supabase.set_table_data("wallets", [SAMPLE_WALLET])
        resp = admin_client.get("/api/admin/financials/wallets?owner_type=therapist")
        assert resp.status_code == 200

    def test_list_wallets_therapist_forbidden(self, client):
        """Therapist cannot list all wallets."""
        resp = client.get("/api/admin/financials/wallets")
        assert resp.status_code == 403


class TestSetCommissionOverride:
    """POST /api/admin/financials/commissions"""

    def test_set_commission(self, admin_client):
        """Admin sets a commission override."""
        admin_client._mock_supabase.set_table_data(
            "platform_commission_overrides", [SAMPLE_COMMISSION_OVERRIDE]
        )
        resp = admin_client.post("/api/admin/financials/commissions", json={
            "target_type": "clinic",
            "target_id": "clinic-001",
            "custom_commission_pct": "8.0",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_set_commission_therapist_forbidden(self, client):
        """Therapist cannot set commission overrides."""
        resp = client.post("/api/admin/financials/commissions", json={
            "target_type": "clinic",
            "target_id": "clinic-001",
            "custom_commission_pct": "8.0",
        })
        assert resp.status_code == 403


class TestListPayouts:
    """GET /api/admin/financials/payouts"""

    def test_list_payouts(self, admin_client):
        """Admin lists all payouts."""
        admin_client._mock_supabase.set_table_data("payouts", [SAMPLE_PAYOUT])
        resp = admin_client.get("/api/admin/financials/payouts")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_payouts_with_status_filter(self, admin_client):
        """Filter by status."""
        admin_client._mock_supabase.set_table_data("payouts", [SAMPLE_PAYOUT])
        resp = admin_client.get("/api/admin/financials/payouts?status=pending")
        assert resp.status_code == 200

    def test_list_payouts_therapist_forbidden(self, client):
        """Therapist cannot list payouts."""
        resp = client.get("/api/admin/financials/payouts")
        assert resp.status_code == 403


class TestProcessPayout:
    """POST /api/admin/financials/payouts/:id/process"""

    def test_process_payout(self, admin_client):
        """Admin processes a pending payout."""
        admin_client._mock_supabase.set_table_data("payouts", [SAMPLE_PAYOUT])
        admin_client._mock_supabase.set_table_data("wallets", [])
        admin_client._mock_supabase.set_table_data("wallet_movements", [])
        resp = admin_client.post("/api/admin/financials/payouts/payout-001/process")
        assert resp.status_code == 200

    def test_process_payout_therapist_forbidden(self, client):
        """Therapist cannot process payouts."""
        resp = client.post("/api/admin/financials/payouts/payout-001/process")
        assert resp.status_code == 403

    def test_process_payout_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/admin/financials/payouts/payout-001/process")
        assert resp.status_code == 401
